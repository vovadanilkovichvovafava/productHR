import { copyOrShowLink } from '@/utils/copyOrShowLink';
import { useState, useEffect, useMemo, useCallback, useRef, Suspense, lazy } from 'react';

import { useNavigate } from 'react-router-dom';
import { useLiveSearchParams } from '@/hooks/useLiveSearchParams';
import {
  Plus,
  Briefcase,
  Users,
  X,
  Loader2,
  Menu,
  PanelLeftOpen,
  FileText,
  Copy,
  Check,
  Tag,
  Pencil,
  Lock,
  MapPin,
  ExternalLink,
  Phone,
  Send,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { useVacancyStore } from '@/stores/vacancyStore';
import { useAuthStore } from '@/stores/authStore';
import { deleteApplication, getEntityFiles, declineVacancy } from '@/services/api';

import { createCandidateShareLink } from '@/services/api/entities';
import { useCardActions } from '@/components/entities/candidateDetail/useCardActions';
import { useFunnelStages } from '@/components/funnels/useFunnelStages';
import { useFunnelVacancyList } from '@/components/funnels/useFunnelVacancyList';
import { FunnelsRecruiterSidebar } from '@/components/funnels/FunnelsRecruiterSidebar';
import { FunnelsVacancyOverview } from '@/components/funnels/FunnelsVacancyOverview';
import { FunnelStageTabs } from '@/components/funnels/FunnelStageTabs';
import VacancyConfirmModal from '@/components/vacancies/VacancyConfirmModal';
import { FunnelCandidateList } from '@/components/funnels/FunnelCandidateList';
import type { Tag as TagType } from '@/services/api/tags';
import { useFunnelVacancyAccess } from '@/components/funnels/useFunnelVacancyAccess';
import { useFunnelEntityData } from '@/components/funnels/useFunnelEntityData';
import { useFunnelCandidates } from '@/components/funnels/useFunnelCandidates';
import { useFunnelSelection } from '@/components/funnels/useFunnelSelection';
import { FUNNEL_STAGE_ORDER, STAGE_LABEL_BY_STAGE } from '@/constants/hrStages';
import TakeCandidateButton from '@/components/entities/TakeCandidateButton';
import TagPicker from '@/components/entities/TagPicker';
import { isPersonallyActive } from '@/utils/vacancy';

import type { Vacancy, VacancyApplication, ApplicationStage } from '@/types';

import { VacancyForm } from '@/components/vacancies';
import CandidateHandoverModal from '@/components/vacancies/CandidateHandoverModal';
import { createApplication } from '@/services/api/vacancies';

import type { KanbanCard } from '@/services/api/candidates';
import ShadowDuplicateBanner from '@/components/entities/ShadowDuplicateBanner';
import { PriorRejectionPanel, usePriorRejectionGate, useVisiblePriorRejections } from '@/components/candidates/priorRejection';
import CandidateVacancyCard from '@/components/entities/CandidateVacancyCard';

import ResumeTab from '@/components/entities/candidateDetail/ResumeTab';
import { buildStageContainers, readSystemHrTags, type StageContainer } from '@/components/entities/candidateDetail/model';
import { EditCandidateModal } from '@/components/candidates/EditCandidateModal';
import { HuntflowInfoRow } from '@/components/hr/HuntflowControls';

import { useFormBadgeStore } from '@/stores/formBadgeStore';
import {
  getEntityFormsUnreadCount,
  getEntityAllDispatches,
  markEntityDispatchesSeen,
  type FormDispatchInfo,
} from '@/services/api/forms';
import { AnketaResponses } from '@/features/forms/AnketaResponses';
import { FunnelRecruiterFilter } from '@/components/funnels/FunnelRecruiterFilter';
import { useMobileMasterDetail } from '@/components/candidates/useMobileMasterDetail';
import { MobileBackToList } from '@/components/candidates/MobileBackToList';

const AnketaDrawer = lazy(() =>
  import('@/features/forms/AnketaDrawer').then((m) => ({ default: m.AnketaDrawer })),
);

// ==================== Constants ====================

// Вкладки, подписи и цвета этапов — общий справочник (constants/hrStages.ts).
const STAGE_ORDER = FUNNEL_STAGE_ORDER;

const STAGE_LABELS: Record<string, string> = {
  ...STAGE_LABEL_BY_STAGE,
  new: STAGE_LABEL_BY_STAGE.applied,
};

const getCandidateFallbackInitial = (name?: string | null) =>
  name?.match(/[0-9A-Za-zА-Яа-яЁё]/)?.[0]?.toUpperCase() || '?';

// ==================== Copy Button Helper ====================

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(value).then(() => {
      toast.success('Скопировано');
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button
      onClick={handleCopy}
      className="p-0.5 rounded text-[var(--hf-dark-600)] hover:text-[var(--hf-dark-300)] transition-colors opacity-0 group-hover:opacity-100"
      title="Копировать"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-[var(--hf-status-green)]" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

// ==================== Main Component ====================

export default function RecruiterFunnelsPage() {
  const navigate = useNavigate();
  // Правки адреса — от ЖИВОГО window.location: клик по этапу и зеркало открытого
  // кандидата пишут в одном такте, и снимок прошлой отрисовки возвращал прежний
  // ?stage= — вкладка «отскакивала» (см. useLiveSearchParams).
  const [searchParams, setSearchParams] = useLiveSearchParams();
  const { vacancies, isLoading, fetchVacancies, updateVacancy, deleteVacancy } = useVacancyStore();
  const { user } = useAuthStore();

  const isHrAdmin = user?.role === 'superadmin' || user?.org_role === 'owner' || user?.org_role === 'admin';
  const isSuperadmin = user?.role === 'superadmin';

  // UI state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showHandover, setShowHandover] = useState(false);
  const [editingVacancy, setEditingVacancy] = useState<Vacancy | null>(null);
  const [mobileSidebar, setMobileSidebar] = useState(false);
  const mobile = useMobileMasterDetail('hf-mobile-view:funnels');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Список вакансий: фильтры, группы рекрутёров, меню (useFunnelVacancyList).
  const vacancyList = useFunnelVacancyList({
    vacancies, fetchVacancies, user, isHrAdmin, searchParams, setSearchParams,
    selectedVacancyId: searchParams.get('v') ? Number(searchParams.get('v')) : null,
  });
  const {
    statusFilter,
    selectedRecruiterFilter, setSelectedRecruiterFilter, 
  } = vacancyList;

  // ClickUp view: selected vacancy + candidates
  const selectedVacancyId = searchParams.get('v') ? Number(searchParams.get('v')) : null;
  const [candidateSearch, setCandidateSearch] = useState('');

  // Bulk selection state
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkMoving, setBulkMoving] = useState(false);

  // Master-detail state
  // Метки кандидата (TagPicker пишет сюда) — уходят в карточку окна «Редактировать».
  const [entityTags, setEntityTags] = useState<TagType[]>([]);
  // По умолчанию 'resume' — как в «Все кандидаты» (detailTab там тоже стартует
  // с "resume"): резюме видно сразу прокруткой, без клика по вкладке. 'info'
  // здесь ничего не рендерит (тут нет отдельной вкладки «Личные заметки»,
  // комментарий пишется прямо в композере таймлайна) — де-факто был мёртвым
  // состоянием, из-за которого низ панели оставался пустым до первого клика.
  const [detailTab, setDetailTab] = useState<'info' | 'resume' | 'anketa'>('resume');
  const [editingCandidateCard, setEditingCandidateCard] = useState<KanbanCard | null>(null);
  const [anketaOpen, setAnketaOpen] = useState(false);
  // Кандидат, для которого открыт дровер «Анкета» — фиксируется в МОМЕНТ клика
  // «Анкета», а не читается вживую из selectedCandidate. Раньше дровер был
  // привязан к live selectedCandidate: пока рекрутёр держит дровер открытым
  // (AI-диалог/конструктор — не мгновенно), несколько эффектов страницы могут
  // молча переключить selectedCandidateId (авто-выбор первого в табе при смене
  // этапа/вкладки, адопт ?entity= из URL) — и анкета уходила уже ДРУГОМУ
  // кандидату, хотя дровер не закрывался. Причина жалобы «анкета прилетает не
  // в ту карточку».
  const [anketaTarget, setAnketaTarget] = useState<{ id: number; name: string } | null>(null);

  // Яркие теги-ярлыки у имени (редактор в воронке).

  // "Add to vacancy" dropdown state
  const [showAddToVacancy, setShowAddToVacancy] = useState(false);
  const [addingToVacancy, setAddingToVacancy] = useState(false);
  const addToVacancyRef = useRef<HTMLDivElement>(null);

  // Selected vacancy — сначала ищем в загруженном списке пользователя.
  const listedVacancy = useMemo(
    () => vacancies.find((v) => v.id === selectedVacancyId),
    [vacancies, selectedVacancyId],
  );

  // Воронка из адреса: из загруженного списка или точечным запросом — с явным
  // экраном «нет доступа / не найдена» (useFunnelVacancyAccess).
  const { selectedVacancy, funnelBlocked, vacancyAccessError, vacancyProbing } =
    useFunnelVacancyAccess(selectedVacancyId, listedVacancy);

  // Закрытая (архивная) вакансия открывается тем же полноценным окном, что и
  // активная (просмотр, резюме, история) — но любая попытка её изменить
  // (смена этапа, комментарий, файл, снятие с воронки) блокируется тостом.
  const vacancyArchived = selectedVacancy?.status === 'closed';
  const blockIfArchived = useCallback(() => {
    if (vacancyArchived) {
      toast.error('Вакансия находится в архиве');
      return true;
    }
    return false;
  }, [vacancyArchived]);

  // Кандидаты открытой воронки: фильтр «Рекрутёр: …», режим шаринг-ссылки,
  // загрузка и тихий опрос (useFunnelCandidates).
  const {
    candidates, setCandidates, candidatesLoading, loadCandidates, loadSeqRef,
    recruiterScopedCandidates, filteredCandidates,
    viewOwner, setViewOwner, recruiterOptions,
  } = useFunnelCandidates({
    selectedVacancyId, selectedVacancy, funnelBlocked, user, isSuperadmin,
    selectedRecruiterFilter, candidateSearch, searchParams, setSearchParams, fetchVacancies,
    onVacancyOpened: () => {
      setSelectedCandidateId(null);
      // Дефолтную вкладку выставляет эффект авто-выбора (гейт по id воронки).
      setDetailTab('resume');
      setSelectedIds(new Set());
    },
  });

  // Этапы воронки: свои колонки вакансии или общий порядок, подписи организации.
  const { stagesConfig, getVacancyStageLabel, vacancyStageDropdownLabels } =
    useFunnelStages(selectedVacancy);

  // Вкладка, выбранный кандидат и связь с адресом (?stage=, ?entity=) —
  // правила «пустой панели» и «открылся не тот» под тестами (useFunnelSelection).
  const {
    selectedTab, selectedCandidateId, setSelectedCandidateId, setStickyCandidateId,
    selectedCandidate, selectStageTab,
    groupedByStageMap, vacancyVisibleStageKeys, tabFilteredCandidates, orderedCandidates,
  } = useFunnelSelection({
    candidates, filteredCandidates, candidateSearch, stagesConfig, selectedVacancyId,
    searchParams, setSearchParams,
    onCandidateFocused: () => setDetailTab('resume'),
  });

  // Бейдж непрочитанных анкет (entity-уровень) — как в «Все кандидаты».
  const anketaCount = useFormBadgeStore((s) => s.counts[selectedCandidate?.entity_id ?? 0] ?? 0);
  const setAnketaCount = useFormBadgeStore((s) => s.setCount);
  useEffect(() => {
    const eid = selectedCandidate?.entity_id;
    if (!eid) return;
    getEntityFormsUnreadCount(eid)
      .then((r) => setAnketaCount(eid, r.count))
      .catch(() => {});
  }, [selectedCandidate?.entity_id, setAnketaCount]);

  // Данные открытого кандидата: лента по воронкам, файлы, extra_data, карточка
  // для баннера дублей и тихий опрос (useFunnelEntityData).
  const {
    activityState, refreshActivity,
    entityFiles, setEntityFiles, filesLoading,
    entityExtraData, setEntityExtraData, dupCard, setDupCard,
    hasResume, resumeSources, resumeIndex, setResumeIndex,
  } = useFunnelEntityData(selectedCandidate?.entity_id ?? null, fetchVacancies);

  // Handlers
  const selectVacancy = (vacancyId: number) => {
    const params: Record<string, string> = { v: String(vacancyId) };
    if (statusFilter !== 'all') params.status = statusFilter;
    // Сохраняем выбранного рекрутёра — иначе при открытии воронки скоуп
    // кандидатов по рекрутёру сбрасывался, и админ видел ВСЕХ (баг 2026-07-13).
    const recruiter = searchParams.get('recruiter');
    if (recruiter) params.recruiter = recruiter;
    setSearchParams(params);
    setCandidateSearch('');
    setMobileSidebar(false);
  };

  const deselectVacancy = () => {
    const params: Record<string, string> = {};
    if (statusFilter !== 'all') params.status = statusFilter;
    const recruiter = searchParams.get('recruiter');
    if (recruiter) params.recruiter = recruiter;
    setSearchParams(params);
  };

  // Confirmation modal — единый для close/delete (window.confirm не везде работает в headless/iframe).
  const [confirmDialog, setConfirmDialog] = useState<{
    type: 'close' | 'leave' | 'delete';
    vacancy: Vacancy;
  } | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);

  const handleCloseVacancy = (vacancy: Vacancy) => {
    setConfirmDialog({ type: 'close', vacancy });
  };

  // «Выйти из вакансии» — снять себя, у остальных она остаётся в работе.
  // Отдельно от «Закрыть вакансию», которая закрывает у всех (2026-09-10).
  const handleLeaveVacancy = (vacancy: Vacancy) => {
    setConfirmDialog({ type: 'leave', vacancy });
  };

  const handleDeleteVacancy = (vacancy: Vacancy) => {
    setConfirmDialog({ type: 'delete', vacancy });
  };

  const runConfirmedAction = async () => {
    if (!confirmDialog) return;
    setConfirmBusy(true);
    try {
      if (confirmDialog.type === 'leave') {
        await declineVacancy(confirmDialog.vacancy.id);
        toast.success('Вы вышли из вакансии — у остальных она осталась в работе');
        fetchVacancies();
      } else if (confirmDialog.type === 'close') {
        await updateVacancy(confirmDialog.vacancy.id, { status: 'closed' });
        toast.success('Вакансия закрыта');
        fetchVacancies();
      } else {
        await deleteVacancy(confirmDialog.vacancy.id);
        toast.success('Вакансия удалена');
        // НЕ рефетчим после удаления: store уже убрал вакансию из списка.
        // Рефетч сразу после delete мог вернуть её обратно из-за read-after-write
        // задержки (реплика/кэш) — отсюда «удаляется только со второго раза».
        if (selectedVacancyId === confirmDialog.vacancy.id) {
          setSearchParams({});
        }
      }
      setConfirmDialog(null);
    } catch {
      toast.error(
        confirmDialog.type === 'leave' ? 'Не удалось выйти из вакансии'
          : confirmDialog.type === 'close' ? 'Ошибка при закрытии' : 'Ошибка при удалении',
      );
    } finally {
      setConfirmBusy(false);
    }
  };

  // Прошлый этап для отката — from_stage самой свежей записи истории
  // (to_stage у неё = текущий этап).
  const handleRemoveFromVacancy = useCallback(async () => {
    if (blockIfArchived()) return;
    const targetAppId = selectedCandidate?.id;
    if (!targetAppId) return;
    // entity_id целевого кандидата (по отклику в списке или по выбранному).
    const targetEntityId =
      candidates.find((c) => c.id === targetAppId)?.entity_id
      ?? selectedCandidate?.entity_id;
    if (!targetEntityId) return;
    // Снимаем ВСЕ отклики этого кандидата на текущую вакансию (а не один по id):
    // дубли откликов (из мержа/импорта) показываются отдельными карточками, и
    // удаление по одному id заставляло «снимать одного и того же дважды».
    const appIds = candidates
      .filter((c) => c.entity_id === targetEntityId)
      .map((c) => c.id);
    if (appIds.length === 0) return;
    try {
      for (const id of appIds) {
        await deleteApplication(id);
      }
      const idsSet = new Set(appIds);
      setCandidates((prev) => prev.filter((c) => !idsSet.has(c.id)));
      loadSeqRef.current++; // инвалидируем in-flight загрузки — иначе focus-refresh вернёт снятого
      toast.success('Кандидат убран из вакансии');
      await refreshActivity();
    } catch {
      toast.error('Не удалось убрать из вакансии');
    }
  }, [selectedCandidate, candidates, refreshActivity, blockIfArchived]);

  // Этапы для пикера — тот же список и лейблы, что были в StageDropdown.
  const stagePickerOptions = useMemo(
    () =>
      STAGE_ORDER.map((stage) => ({
        status: stage as ApplicationStage,
        label: vacancyStageDropdownLabels[stage] || STAGE_LABELS[stage] || stage,
      })),
    [vacancyStageDropdownLabels],
  );

  // Действия карточки — общие с «Все кандидаты» (useCardActions). Здесь только
  // то, чем воронка отличается: extra_data кандидата — своё состояние страницы,
  // комментарий привязан к ЭТОЙ воронке (у каждой воронки своя лента), откат
  // перевода переставляет карточку в списке воронки.
  const cardActions = useCardActions({
    entityId: selectedCandidate?.entity_id,
    isBlocked: blockIfArchived,
    patchExtra: (update) => setEntityExtraData((prev) => update(prev || {})),
    replaceExtra: (fresh) => setEntityExtraData(fresh),
    refreshActivity,
    reloadFiles: async (eid) => setEntityFiles(await getEntityFiles(eid)),
    noteVacancyId: () => selectedVacancyId,
    onRolledBack: ({ appId, stage }) => {
      if (appId == null || !stage) return;
      const back = stage as ApplicationStage;
      setCandidates((prev) =>
        prev.map((c) => (c.id === appId ? { ...c, stage: back } : c)),
      );
      loadSeqRef.current++; // in-flight поллинг не должен вернуть старый этап
      setStickyCandidateId(appId);
      fetchVacancies();
      return `Перевод отменён — кандидат снова на «${getVacancyStageLabel(back)}»`;
    },
  });

  // Смена этапа из карточки: перевод — общий (cardActions), здесь только
  // перестановка в списке воронки.
  const cardChangeStage = useCallback(
    async (appId: number, stage: string, comment?: string) => {
      const newStage = stage as ApplicationStage;
      const { ok } = await cardActions.changeApplicationStage(appId, newStage, comment);
      if (ok) {
        // Двигаем кандидата на месте + СРАЗУ снимаем «предыдущую серию»: смена
        // этапа обновляет last_stage_change_at, отклик уходит из серой зоны.
        setCandidates((prev) =>
          prev.map((c) => (c.id === appId ? { ...c, stage: newStage, is_previous_series: false } : c)),
        );
        // Инвалидируем in-flight поллинг: его ответ со СТАРЫМ этапом иначе
        // откатил бы карточку назад на ~15с (аудит 2026-08-07).
        loadSeqRef.current++;
        // Вкладку не переключаем и перемещённого не выбрасываем из списка:
        // рекрутёр остаётся на его карточке (2026-09-23, разбор Huntflow).
        // Тоста нет намеренно — этап виден прямо в карточке.
        setStickyCandidateId(appId);
        fetchVacancies(); // счётчики вакансий
      }
      await refreshActivity();
      return ok;
    },
    [cardActions, refreshActivity, fetchVacancies],
  );

  // ─── Общая богатая карточка «Все кандидаты» (CandidateVacancyCard) в детали
  // воронки. Строим KanbanCard-форму из selectedCandidate + entityExtraData и
  // стек контейнеров через ту же чистую модель buildStageContainers, что и
  // AllCandidatesPage — без форка поведения. ───
  const funnelCard = useMemo<KanbanCard | null>(() => {
    if (!selectedCandidate) return null;
    return {
      // dupCard уже несёт полный набор полей кандидата (email/phone/telegram_
      // username/position/company/city/age/salary/total_experience/source/
      // source_url) — тот же getEntity(), что грузится для баннера дублей.
      // Раньше funnelCard собирался «голым» (только id/name/created_at/tags),
      // из-за чего карточка в воронке была заметно беднее, чем в «Все
      // кандидаты» (не было возраста/города/опыта/компании/телеграма,
      // источник не был кликабельной ссылкой).
      ...dupCard,
      id: selectedCandidate.entity_id,
      name: selectedCandidate.entity_name || '',
      created_at: selectedCandidate.applied_at,
      tags: dupCard?.tags || [],
      // Комменты СКОУПИМ по воронке: показываем только заметки ЭТОЙ вакансии
      // (vacancy_id === selectedVacancyId) + «Общие» (без vacancy_id / легаси).
      // Один кандидат в нескольких воронках — у каждой своя лента комментов.
      // По автору НЕ фильтруем: все видят комментарии всех, кто работает в этой
      // воронке, — как на «Все кандидаты» (решение юзера 2026-09-15; раньше
      // рекрутёр видел только свои, и отказ Марии в её воронке у коллег пропадал).
      extra_data: (() => {
        const ed = (entityExtraData || {}) as Record<string, unknown>;
        const allNotes = Array.isArray(ed.notes) ? (ed.notes as Array<Record<string, unknown>>) : null;
        if (!allNotes) return ed;
        const scoped = allNotes.filter(
          (n) => n?.vacancy_id == null || n.vacancy_id === selectedVacancyId,
        );
        return { ...ed, notes: scoped };
      })(),
    };
  }, [selectedCandidate, entityExtraData, dupCard, selectedVacancyId]);

  // Ярлыки у ФИО редактирует TagPicker (variant='headline') — он сам ходит в
  // справочник меток. Здесь остаётся только запрет для «Наблюдателя».
  const hlReadonly = !!user?.is_readonly;

  // «Первичный» блок = заявка на текущую вакансию воронки (если определима),
  // иначе первый блок активности. Его applicationId/events/vacancyTitle уходят в
  // живой контейнер; статус живого = статус самого кандидата (его текущий этап).
  // Только лента ВЫБРАННОГО кандидата — чужая (ещё не сменившаяся) не годится.
  const entityActivity = useMemo(
    () => (activityState.entityId === (selectedCandidate?.entity_id ?? null) ? activityState.blocks : []),
    [activityState, selectedCandidate?.entity_id],
  );
  const primaryBlock = useMemo(() => {
    if (entityActivity.length === 0) return undefined;
    return (
      entityActivity.find((b) => b.application_id === selectedCandidate?.id)
      || entityActivity.find((b) => b.vacancy_id === selectedVacancyId)
      || entityActivity[0]
    );
  }, [entityActivity, selectedVacancyId, selectedCandidate?.id]);

  const containers = useMemo<StageContainer[]>(() => {
    if (!funnelCard) return [];
    return buildStageContainers({
      card: funnelCard,
      status: selectedCandidate?.stage || primaryBlock?.current_stage || 'applied',
      // В воронке выбранный кандидат И ЕСТЬ заявка этой воронки — берём её id
      // напрямую, а не из ленты (защита от смены этапа чужой заявке).
      liveApplicationId:
        (selectedCandidate && selectedCandidate.vacancy_id === selectedVacancyId ? selectedCandidate.id : undefined)
        ?? primaryBlock?.application_id ?? 0,
      liveEvents: primaryBlock?.events,
      liveVacancyTitle: primaryBlock?.vacancy_title ?? null,
      allEntityFiles: entityFiles,
      livePinnedEntryKey: primaryBlock?.pinned_entry_key ?? null,
    });
  }, [funnelCard, selectedCandidate?.stage, selectedCandidate?.id, selectedCandidate?.vacancy_id, selectedVacancyId, primaryBlock, entityFiles]);

  // Toggle checkbox selection for a candidate
  const toggleCandidateSelection = useCallback((candidateId: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(candidateId)) next.delete(candidateId);
      else next.add(candidateId);
      return next;
    });
  }, []);

  // Bulk «Удалить с воронки» — удаляет выбранных кандидатов из текущей вакансии.
  const handleBulkRemoveFromVacancy = useCallback(async () => {
    if (blockIfArchived()) return;
    if (selectedIds.size === 0) return;
    // entity_id выбранных карточек → затем ВСЕ их отклики на этой вакансии (на
    // случай дублей из мержа), иначе дубль остался бы после снятия.
    const selectedEntityIds = new Set(
      candidates.filter((c) => selectedIds.has(c.id)).map((c) => c.entity_id),
    );
    if (!window.confirm(`Удалить ${selectedEntityIds.size} кандидат(ов) с воронки?`)) return;
    setBulkMoving(true);
    try {
      const ids = candidates
        .filter((c) => selectedEntityIds.has(c.entity_id))
        .map((c) => c.id);
      for (const id of ids) {
        await deleteApplication(id);
      }
      const idsSet = new Set(ids);
      setCandidates((prev) => prev.filter((c) => !idsSet.has(c.id)));
      loadSeqRef.current++; // инвалидируем in-flight загрузки
      setSelectedIds(new Set());
      toast.success(`${selectedEntityIds.size} кандидат(ов) удалено с воронки`);
      fetchVacancies();
    } catch (err) {
      // Показываем реальную причину с бэкенда (например, недостаточно прав).
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'Ошибка при удалении с воронки');
    } finally {
      setBulkMoving(false);
    }
  }, [selectedIds, candidates, fetchVacancies, blockIfArchived]);

  const anySelected = selectedIds.size > 0;

  // Close "add to vacancy" dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (addToVacancyRef.current && !addToVacancyRef.current.contains(e.target as Node)) {
        setShowAddToVacancy(false);
      }
    };
    if (showAddToVacancy) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showAddToVacancy]);

  // Get vacancies available for adding a candidate (exclude current vacancy, show only open ones)
  const availableVacanciesForCandidate = useMemo(() => {
    if (!selectedCandidate?.entity_id) return [];
    // Заявка-оригинал после «Взять в работу» переходит в open и висит рядом со
    // своим клоном (рабочей вакансией) → дубль («Трафик» ×2). Прячем оригиналы,
    // у которых уже есть клон — как это делает сайдбар и AddToVacancyModal.
    const clonedSourceIds = new Set<number>();
    vacancies.forEach((v) => {
      const src = (v.extra_data as Record<string, unknown> | undefined)
        ?.cloned_from_request_id;
      if (typeof src === 'number') clonedSourceIds.add(src);
    });
    return vacancies.filter(v =>
      v.id !== selectedVacancyId &&
      v.status === 'open' &&
      !clonedSourceIds.has(v.id) &&
      // Свои воронки = где ЛИЧНО принял (isPersonallyActive, 2026-07-08) —
      // назначенный, но ещё не нажавший «Взять в работу», не должен
      // перекидывать кандидатов в воронку, к которой сам ещё не присоединился.
      (isHrAdmin || (!!user && isPersonallyActive(v, user.id)))
    );
  }, [vacancies, selectedVacancyId, selectedCandidate?.entity_id, isHrAdmin, user]);

  const buildCandidateEditCard = useCallback((candidate: VacancyApplication): KanbanCard => ({
    id: candidate.entity_id,
    name: candidate.entity_name || 'Без имени',
    email: candidate.entity_email || undefined,
    phone: candidate.entity_phone || undefined,
    telegram_username: candidate.entity_telegram || undefined,
    position: candidate.entity_position || undefined,
    source: candidate.source || undefined,
    recruiter_name: selectedVacancy?.created_by_name,
    created_at: candidate.applied_at,
    tags: entityTags.map((tag) => tag.name),
    company: candidate.entity_company || undefined,
    vacancy_name: selectedVacancy?.title || candidate.vacancy_title,
    rejection_reason: candidate.rejection_reason || undefined,
    extra_data: entityExtraData || undefined,
  }), [entityExtraData, entityTags, selectedVacancy]);

  const handleCandidateSaved = useCallback((updated: Partial<KanbanCard>) => {
    if (!editingCandidateCard) return;
    setCandidates((items) => items.map((candidate) => (
      candidate.entity_id === editingCandidateCard.id
        ? {
            ...candidate,
            entity_name: updated.name ?? candidate.entity_name,
            entity_email: updated.email ?? candidate.entity_email,
            entity_phone: updated.phone ?? candidate.entity_phone,
            entity_telegram: updated.telegram_username ?? candidate.entity_telegram,
            entity_position: updated.position ?? candidate.entity_position,
            entity_company: updated.company ?? candidate.entity_company,
          }
        : candidate
    )));
    // entityExtraData/dupCard — ОТДЕЛЬНОЕ состояние (грузится через getEntity()
    // только при смене selectedCandidate, см. useEffect выше), сохранение
    // кандидата его не трогало. Из-за этого дата рождения/возраст (funnelCard.age,
    // и сама форма при повторном открытии — buildCandidateEditCard берёт
    // entityExtraData) продолжали показывать старые значения до перевыбора
    // кандидата. Мержим extra_data из ответа сохранения сразу.
    if (updated.extra_data) {
      setEntityExtraData((prev) => ({ ...(prev || {}), ...updated.extra_data }));
      setDupCard((prev) => (prev ? {
        ...prev,
        extra_data: { ...(prev.extra_data || {}), ...updated.extra_data },
        age: updated.extra_data?.age != null ? String(updated.extra_data.age) : prev.age,
      } : prev));
    }
    setEditingCandidateCard(null);
  }, [editingCandidateCard]);

  // «Этот кандидат уже получал отказ — всё равно добавить?» (22.10.2026).
  const priorGate = usePriorRejectionGate();
  const priorGateFn = priorGate.gate;
  const funnelPriorRejections = useVisiblePriorRejections(selectedCandidate?.entity_id, selectedCandidate?.vacancy_id);

  // Handle adding candidate to another vacancy
  const handleAddToVacancy = useCallback(async (targetVacancyId: number) => {
    if (!selectedCandidate?.entity_id) return;
    if (!(await priorGateFn(selectedCandidate.entity_id))) return;
    setAddingToVacancy(true);
    try {
      // ADD (не MOVE): кандидат ДОБАВЛЯЕТСЯ в вакансию, НЕ снимаясь с других —
      // один кандидат может быть в нескольких воронках сразу (по запросу HR).
      // create_application аддитивен и сам не даёт дубля в той же вакансии (400).
      await createApplication(targetVacancyId, { vacancy_id: targetVacancyId, entity_id: selectedCandidate.entity_id, source: 'manual_add' });
      const targetVacancy = vacancies.find(v => v.id === targetVacancyId);
      toast.success(`Кандидат добавлен в «${targetVacancy?.title || targetVacancyId}»`);
      // НЕ закрываем меню и НЕ снимаем выбор — можно докинуть в ещё вакансии.
      if (selectedVacancyId) loadCandidates(selectedVacancyId);
      fetchVacancies();
    } catch (err: any) {
      const detail = err?.response?.data?.detail || '';
      // Уже в этой вакансии — не ошибка, дружелюбная подсказка.
      if (typeof detail === 'string' && detail.includes('уже добавлен')) {
        toast('Кандидат уже в этой вакансии');
      } else {
        toast.error(detail || 'Не удалось добавить в вакансию');
      }
    } finally {
      setAddingToVacancy(false);
    }
  }, [selectedCandidate?.entity_id, vacancies, fetchVacancies, selectedVacancyId, loadCandidates, priorGateFn]);

  // ==================== Render ====================

  return (
    <div className="h-full flex overflow-hidden relative">
      {priorGate.element}
      {/* Mobile sidebar overlay (admin only) */}
      {isHrAdmin && mobileSidebar && (
        <div
          className="lg:hidden fixed inset-0 bg-[var(--hf-black-alpha-50)] z-40"
          onClick={() => setMobileSidebar(false)}
        />
      )}

      {/* ========== LEFT SIDEBAR: Recruiter tree (admin only) ========== */}
      {isHrAdmin && !selectedVacancy && !funnelBlocked && (
        <FunnelsRecruiterSidebar
          list={vacancyList}
          isLoading={isLoading}
          isHrAdmin={isHrAdmin}
          selectedVacancyId={selectedVacancyId}
          selectVacancy={selectVacancy}
          sidebarCollapsed={sidebarCollapsed}
          setSidebarCollapsed={setSidebarCollapsed}
          mobileSidebar={mobileSidebar}
          setMobileSidebar={setMobileSidebar}
          hlReadonly={hlReadonly}
          setShowCreateModal={setShowCreateModal}
        />
      )}

      {/* Expand sidebar button (visible when collapsed, admin only) */}
      {isHrAdmin && !selectedVacancy && !funnelBlocked && sidebarCollapsed && (
        <button
          onClick={() => setSidebarCollapsed(false)}
          className="hf-recruiter-sidebar-expand hidden lg:flex group"
          title="Развернуть панель"
        >
          <PanelLeftOpen className="w-4 h-4 transition-colors" />
        </button>
      )}

      {/* ========== MAIN CONTENT ========== */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Диплинк на недоступную воронку — явный экран вместо обзора своих. */}
        {funnelBlocked ? (
          <div className="flex-1 flex items-center justify-center p-8">
            <div className="max-w-md text-center">
              <div className="w-16 h-16 mx-auto rounded-2xl bg-[var(--hf-white-alpha-06)] border border-[color:var(--hf-white-alpha-10)] flex items-center justify-center mb-4">
                <Lock className="w-7 h-7 text-[var(--hf-dark-500)]" />
              </div>
              <h2 className="text-lg font-semibold text-[var(--hf-dark-200)] mb-2">
                {vacancyAccessError === 'missing'
                  ? 'Воронка не найдена'
                  : 'Нет доступа к этой воронке'}
              </h2>
              <p className="text-sm text-[var(--hf-dark-500)] mb-6">
                {vacancyAccessError === 'missing'
                  ? 'Вакансия удалена или ссылка ведёт в другую организацию.'
                  : 'Ссылка ведёт в воронку другого рекрутёра. Вы видите только те воронки, где вы участник — создатель, назначенный или принявший заявку. Попросите владельца воронки или HR-админа выдать доступ.'}
              </p>
              <button
                type="button"
                onClick={deselectVacancy}
                className="px-5 py-2 rounded-lg text-sm font-medium bg-[var(--hf-cyan-700)] text-white hover:opacity-90"
              >
                К моим вакансиям
              </button>
            </div>
          </div>
        ) : vacancyProbing ? (
          /* Пока проверяем доступ — лоадер, а не обзор своих воронок: иначе
             прежний «отскок на свои ваки» мигал бы перед экраном ошибки. */
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="w-6 h-6 animate-spin text-[var(--hf-dark-500)]" />
          </div>
        ) : !selectedVacancy ? (
          <FunnelsVacancyOverview
            list={vacancyList}
            user={user}
            isHrAdmin={isHrAdmin}
            hlReadonly={hlReadonly}
            selectVacancy={selectVacancy}
            setMobileSidebar={setMobileSidebar}
            setShowCreateModal={setShowCreateModal}
            setShowHandover={setShowHandover}
            setEditingVacancy={setEditingVacancy}
            onCloseVacancy={handleCloseVacancy}
            onLeaveVacancy={handleLeaveVacancy}
            onDeleteVacancy={handleDeleteVacancy}
          />
        ) : (
          /* Vacancy selected — show candidates (Huntflow-style master-detail) */
          <div className="hf-vacancy-workspace flex-1 flex flex-col overflow-hidden">
            {/* Top bar: vacancy title context; search lives in the stage island like /all-candidates */}
            <div className="hf-vacancy-topbar flex flex-col sm:flex-row sm:items-center justify-between px-3 sm:px-5 py-2 sm:py-3 gap-2 border-b border-[color:var(--hf-white-alpha-06)] bg-[var(--hf-white-alpha-02)] flex-shrink-0">
              {/* Breadcrumb */}
              <div className="flex items-center gap-1.5 text-sm min-w-0">
                <button
                  onClick={() => setMobileSidebar(true)}
                  className="lg:hidden p-1.5 -ml-1 rounded-lg hover:bg-[var(--hf-white-alpha-06)] transition-colors flex-shrink-0"
                >
                  <Menu className="w-4 h-4 text-[var(--hf-dark-400)]" />
                </button>
                <button
                  onClick={deselectVacancy}
                  className="sm:hidden text-[var(--hf-dark-500)] hover:text-[var(--hf-dark-300)] transition-colors text-xs"
                >
                  ← Назад
                </button>
                <span className={clsx(
                  'hf-vacancy-title',
                  'font-medium truncate max-w-[180px] sm:max-w-[250px]',
                  selectedVacancy.title?.trim() ? 'text-[var(--hf-dark-200)]' : 'text-[var(--hf-dark-500)] italic',
                )}>
                  {selectedVacancy.title?.trim() || 'Без названия'}{selectedVacancy.department_name ? ` · ${selectedVacancy.department_name}` : ''}
                </span>
                <span className="hf-vacancy-counter text-xs text-[var(--hf-dark-500)] ml-1 sm:ml-2 flex-shrink-0">
                  {recruiterScopedCandidates.length}
                </span>
              </div>

            </div>

            {candidatesLoading ? (
              <div className="flex items-center justify-center py-16 flex-1">
                <div className="w-6 h-6 border-2 border-[var(--hf-accent)] border-t-transparent rounded-full animate-spin" />
              </div>
            ) : (
              /* ===== DETAIL VIEW: Huntflow-style master-detail ===== */
              <>
                <FunnelStageTabs
                  candidateSearch={candidateSearch}
                  setCandidateSearch={setCandidateSearch}
                  groupedByStageMap={groupedByStageMap}
                  selectStageTab={selectStageTab}
                  selectedTab={selectedTab}
                  selectedVacancy={selectedVacancy}
                  setEditingVacancy={setEditingVacancy}
                  stagesConfig={stagesConfig}
                  vacancyVisibleStageKeys={vacancyVisibleStageKeys}
                />
                {/* Чьих кандидатов показываем — ПОСТОЯННАЯ полоса над контентом (а не
                    в списке): фильтр виден на любом этапе, и когда этап пуст. */}
                <div className="flex items-center px-3 sm:px-5 py-2 border-b border-[color:var(--hf-white-alpha-06)] flex-shrink-0">
                  <FunnelRecruiterFilter
                    viewOwner={viewOwner}
                    setViewOwner={setViewOwner}
                    options={recruiterOptions}
                    myId={user?.id}
                    allIsDefault={isSuperadmin || !!user?.is_readonly}
                  />
                </div>

                {tabFilteredCandidates.length === 0 && !candidateSearch.trim() ? (
                  <div className="hf-vacancy-empty flex-1 overflow-y-auto">
                    <section className="hf-vacancy-empty-card">
                      <h2>На этом этапе пока нет кандидатов</h2>
                      <p className="hf-vacancy-empty-text">
                        Кандидаты появятся здесь после перемещения на выбранный этап.
                      </p>
                    </section>
                  </div>
                ) : (
                /* Master-Detail split */
                <div className="hf-candidates-master" data-mobile-view={mobile.view}>
                  {/* Left: candidate list */}
                  <FunnelCandidateList
                    anySelected={anySelected}
                    bulkMoving={bulkMoving}
                    candidates={candidates}
                    fetchVacancies={fetchVacancies}
                    handleBulkRemoveFromVacancy={handleBulkRemoveFromVacancy}
                    hlReadonly={hlReadonly}
                    loadCandidates={loadCandidates}
                    orderedCandidates={orderedCandidates}
                    selectedCandidateId={selectedCandidateId}
                    selectedIds={selectedIds}
                    selectedVacancyId={selectedVacancyId}
                    setDetailTab={setDetailTab}
                    setSearchParams={setSearchParams}
                    setSelectedCandidateId={(id) => {
                      setSelectedCandidateId(id);
                      if (id != null) mobile.showCard();
                    }}
                    setSelectedIds={setSelectedIds}
                    tabFilteredCandidates={tabFilteredCandidates}
                    toggleCandidateSelection={toggleCandidateSelection}
                  />

                  {/* Right: detail panel */}
                  <div className="hf-candidates-detail-panel hf-vacancy-detail flex-1 bg-[var(--hf-white)] hf-dark-disabled:bg-[var(--hf-bg-dark)] rounded-hf-l flex flex-col overflow-hidden">
                    <MobileBackToList onClick={mobile.showList} />
                    {selectedCandidate ? (
                      <>
                        {/* Tab content — единый профиль (как «Все кандидаты»):
                            инфо + история + нижний ряд вкладок Анкеты/Резюме. */}
                        <div className="flex-1 overflow-y-auto">
                          <div className="p-[var(--hf-space-xxl)] max-w-[1220px]">
                              {/* Копипаст резюме (Feature B) идёт через этот же баннер
                                  (strength === "text") — отдельного серого бейджа больше нет. */}
                              {/* Одна плашка: отказ + дубль + «Сравнить» (22.10.2026). */}
                              {dupCard ? (
                                <ShadowDuplicateBanner
                                  card={dupCard}
                                  status={selectedCandidate.stage as string}
                                  onResolved={() => setDupCard(null)}
                                  rejections={funnelPriorRejections}
                                />
                              ) : selectedCandidate.entity_id ? (
                                <div className="mb-3">
                                  <PriorRejectionPanel
                                    entityId={selectedCandidate.entity_id}
                                    ownFunnelsExcept={selectedCandidate.vacancy_id}
                                  />
                                </div>
                              ) : null}
                              {/* Top action buttons — Huntflow style */}
                              <div className="hf-profile-action-bar">
                                {selectedCandidate.entity_id && (
                                  <button
                                    onClick={() => navigate(`/all-candidates?entity=${selectedCandidate.entity_id}`)}
                                    className="hf-profile-action-btn"
                                  >
                                    <Users className="hf-profile-action-icon" /> Открыть профиль
                                  </button>
                                )}
                                {selectedCandidate.entity_id && !hlReadonly && (
                                  <div className="relative" ref={addToVacancyRef}>
                                    <button
                                      onClick={() => setShowAddToVacancy(!showAddToVacancy)}
                                      disabled={addingToVacancy}
                                      className="hf-profile-action-btn disabled:opacity-50"
                                    >
                                      {addingToVacancy ? (
                                        <Loader2 className="hf-profile-action-icon animate-spin" />
                                      ) : (
                                        <Plus className="hf-profile-action-icon" />
                                      )}
                                      Добавить в вакансию
                                    </button>
                                    {showAddToVacancy && (
                                      <div className="hf-profile-vacancy-menu absolute top-full left-0 mt-1 w-72 max-h-64 overflow-y-auto z-50">
                                        {availableVacanciesForCandidate.length === 0 ? (
                                          <div className="hf-profile-vacancy-menu-empty">Нет доступных вакансий</div>
                                        ) : (
                                          availableVacanciesForCandidate.map((v) => (
                                            <button
                                              key={v.id}
                                              onClick={() => handleAddToVacancy(v.id)}
                                              disabled={addingToVacancy}
                                              className="hf-profile-vacancy-menu-item"
                                            >
                                              <Briefcase className="hf-profile-vacancy-menu-icon" />
                                              <span className="truncate">{v.title}</span>
                                            </button>
                                          ))
                                        )}
                                      </div>
                                    )}
                                  </div>
                                )}
                                {selectedCandidate.entity_id && !hlReadonly && (
                                  <TakeCandidateButton
                                    entityId={selectedCandidate.entity_id}
                                    onDone={({ vacancyId, recruiterId }) => {
                                      // Кандидат сменил владельца → он выпадает из
                                      // текущего фильтра рекрутёра и кажется «удалённым».
                                      // Показываем его под НОВЫМ владельцем: если забрали
                                      // в ЭТУ воронку — переключаем фильтр на нового
                                      // (эффект candidateScopeRecruiterId сам перезагрузит).
                                      if (
                                        isHrAdmin &&
                                        vacancyId === selectedVacancyId &&
                                        selectedRecruiterFilter !== recruiterId
                                      ) {
                                        setSelectedRecruiterFilter(recruiterId);
                                        // + синк в URL: иначе эффект URL→state на
                                        // F5/навигации вернёт старый фильтр и
                                        // кандидат снова «пропадёт».
                                        setSearchParams((prev) => {
                                          const next = new URLSearchParams(prev);
                                          next.set('recruiter', String(recruiterId));
                                          return next;
                                        }, { replace: true });
                                      } else if (selectedVacancyId) {
                                        loadCandidates(selectedVacancyId, true);
                                      }
                                      fetchVacancies();
                                    }}
                                  />
                                )}
                                {/* «Поделиться» создаёт публичную ссылку (запись) —
                                    наблюдателю нельзя. */}
                                {selectedCandidate.entity_id && !hlReadonly && (
                                  <button
                                    onClick={async () => {
                                      try {
                                        const link = await createCandidateShareLink(selectedCandidate.entity_id!);
                                        await copyOrShowLink(`${window.location.origin}${link.url_path}`, 'Ссылка на предпросмотр скопирована — действует 30 дней');
                                      } catch {
                                        toast.error('Не удалось создать ссылку');
                                      }
                                    }}
                                    className="hf-profile-action-btn"
                                    title="Скопировать публичную ссылку предпросмотра для заказчика (действует 30 дней)"
                                  >
                                    <ExternalLink className="hf-profile-action-icon" /> Поделиться
                                  </button>
                                )}
                                {!hlReadonly && (
                                <button
                                  onClick={() => setEditingCandidateCard(buildCandidateEditCard(selectedCandidate))}
                                  className="hf-profile-action-btn"
                                >
                                  <Pencil className="hf-profile-action-icon" /> Редактировать
                                </button>
                                )}
                                {!hlReadonly && (
                                <button
                                  onClick={handleRemoveFromVacancy}
                                  className="hf-profile-action-btn"
                                >
                                  <X className="hf-profile-action-icon" /> Удалить с воронки
                                </button>
                                )}
                              </div>

                              {/* Name + large photo (Huntflow / AllCandidatesPage style) */}
                              <div className="hf-profile-summary">
                                <div className="hf-profile-summary-copy">
                                  <div className="flex items-center gap-3 flex-wrap">
                                    <h2 className="hf-profile-title">
                                      {selectedCandidate.entity_name || 'Без имени'}
                                    </h2>
                                    {/* Ярлыки у ФИО — тот же справочник, что и
                                        «Метки» (см. TagPicker variant='headline').
                                        Раньше тут был свободный ввод со своей
                                        палитрой, и один и тот же ярлык в разных
                                        карточках писали по-разному. */}
                                    <TagPicker
                                      entityId={selectedCandidate.entity_id}
                                      variant="headline"
                                      disabled={hlReadonly}
                                    />
                                  </div>
                                  {(() => {
                                    // funnelCard обогащён полным Entity (dupCard) — берём оттуда с
                                    // fallback на «снэпшот»-поля заявки, пока dupCard ещё грузится.
                                    const position = funnelCard?.position || selectedCandidate.entity_position;
                                    const company = funnelCard?.company || selectedCandidate.entity_company;
                                    return (position || company) && (
                                      <p className="hf-profile-subtitle">
                                        {[position, company].filter(Boolean).join(' · ')}
                                      </p>
                                    );
                                  })()}

                              {/* Contact info — Huntflow dotted-line rows */}
                              <div className="mb-[var(--hf-space-xl)]">
                                {selectedCandidate.entity_phone && (
                                  <HuntflowInfoRow label="Телефон">
                                    <div className="flex items-center gap-2">
                                      <a href={`tel:${selectedCandidate.entity_phone}`} className="text-[var(--hf-main-900)] hover:text-[var(--hf-cyan-700)] transition-colors">
                                        {selectedCandidate.entity_phone}
                                      </a>
                                      <CopyButton value={selectedCandidate.entity_phone} />
                                      {/* Мессенджер-иконки — были в «Все кандидаты», но отсутствовали здесь. */}
                                      <a
                                        href={`https://wa.me/${selectedCandidate.entity_phone.replace(/\D/g, '')}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="w-[22px] h-[22px] rounded-full bg-[var(--hf-ui-social-whatsapp)] flex items-center justify-center hover:opacity-80"
                                        title="WhatsApp"
                                      >
                                        <Phone className="w-[11px] h-[11px] text-[var(--hf-white)]" />
                                      </a>
                                      {(funnelCard?.telegram_username || selectedCandidate.entity_telegram) && (
                                        <a
                                          href={`https://t.me/${(funnelCard?.telegram_username || selectedCandidate.entity_telegram || '').replace(/^@/, '')}`}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="w-[22px] h-[22px] rounded-full bg-[var(--hf-ui-social-telegram)] flex items-center justify-center hover:opacity-80"
                                          title="Telegram"
                                        >
                                          <Send className="w-[11px] h-[11px] text-[var(--hf-white)]" />
                                        </a>
                                      )}
                                    </div>
                                  </HuntflowInfoRow>
                                )}
                                {selectedCandidate.entity_email && (
                                  <HuntflowInfoRow label="Эл. почта">
                                    <div className="flex items-center gap-2">
                                      <a href={`mailto:${selectedCandidate.entity_email}`} className="text-[var(--hf-main-900)] hover:text-[var(--hf-cyan-700)] transition-colors">
                                        {selectedCandidate.entity_email}
                                      </a>
                                      <CopyButton value={selectedCandidate.entity_email} />
                                    </div>
                                  </HuntflowInfoRow>
                                )}
                                {(() => {
                                  const telegram = funnelCard?.telegram_username || selectedCandidate.entity_telegram;
                                  return telegram && (
                                    <HuntflowInfoRow label="Telegram">
                                      <div className="flex items-center gap-2">
                                        <a href={`https://t.me/${telegram}`} target="_blank" rel="noopener noreferrer" className="text-[var(--hf-main-900)] hover:text-[var(--hf-cyan-700)] transition-colors">
                                          @{telegram}
                                        </a>
                                        <CopyButton value={`@${telegram}`} />
                                      </div>
                                    </HuntflowInfoRow>
                                  );
                                })()}
                                {funnelCard?.age && (
                                  <HuntflowInfoRow label="Возраст">
                                    <span className="text-[var(--hf-main-900)]">{funnelCard.age}</span>
                                  </HuntflowInfoRow>
                                )}
                                {funnelCard?.city && (
                                  <HuntflowInfoRow label="Город">
                                    <span className="text-[var(--hf-main-900)] inline-flex items-center gap-1">
                                      <MapPin className="w-3.5 h-3.5 text-[var(--hf-main-500)]" />
                                      {funnelCard.city}
                                    </span>
                                  </HuntflowInfoRow>
                                )}
                                {funnelCard?.salary && (
                                  <HuntflowInfoRow label="Зарплата">
                                    <span className="text-[var(--hf-main-900)]">{funnelCard.salary}</span>
                                  </HuntflowInfoRow>
                                )}
                                {funnelCard?.total_experience && (
                                  <HuntflowInfoRow label="Опыт">
                                    <span className="text-[var(--hf-main-900)]">{funnelCard.total_experience}</span>
                                  </HuntflowInfoRow>
                                )}
                                {(() => {
                                  const source = funnelCard?.source || selectedCandidate.source;
                                  const sourceUrl = funnelCard?.source_url;
                                  if (!source && !sourceUrl) return null;
                                  return (
                                    <HuntflowInfoRow label="Источник">
                                      {sourceUrl ? (
                                        <a
                                          href={sourceUrl}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="text-[var(--hf-cyan-700)] hover:text-[var(--hf-red-500)] transition-colors inline-flex items-center gap-1"
                                        >
                                          {source || 'Ссылка'} <ExternalLink className="w-3 h-3" />
                                        </a>
                                      ) : (
                                        <span className="text-[var(--hf-main-900)]">{source}</span>
                                      )}
                                    </HuntflowInfoRow>
                                  );
                                })()}
                                {/* «О себе» — краткое описание кандидата
                                    (extra_data.summary); паритет с «Все кандидаты». */}
                                {(() => {
                                  const s = (funnelCard?.extra_data as Record<string, unknown> | undefined)?.summary;
                                  if (typeof s !== 'string' || !s.trim()) return null;
                                  return (
                                    <HuntflowInfoRow label="О себе">
                                      <span className="whitespace-pre-wrap break-words text-[var(--hf-main-900)]">
                                        {s.trim()}
                                      </span>
                                    </HuntflowInfoRow>
                                  );
                                })()}
                              </div>

                              {/* Tags / Metki */}
                              <div className="mb-6">
                                <div className="flex items-center gap-2 mb-2">
                                  <Tag className="w-3.5 h-3.5 text-[var(--hf-dark-500)]" />
                                  <span className="text-xs font-medium text-[var(--hf-dark-500)] uppercase tracking-wider">Метки</span>
                                </div>
                                <div className="flex flex-wrap items-center gap-1.5">
                                  {/* Авто-метки HR (read-only): кто забрал кандидата в воронку
                                      (extra_data.system_hr_tags). Без крестика — каталожные
                                      метки ниже остаются полностью редактируемыми. */}
                                  {readSystemHrTags(entityExtraData).map((hr) => (
                                    <span
                                      key={`hr-${hr.hr_id}`}
                                      title={hr.source === "board"
                                        ? "Ведущий HR — назначен на доске «Штат»"
                                        : "Закреплённый HR — проставляется автоматически по воронке"}
                                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-[var(--hf-ui-hover)] text-[var(--hf-main-800)] border border-[color:var(--hf-ui-border)]"
                                    >
                                      <Lock className="w-3 h-3 opacity-50" />
                                      HR: {hr.name}{hr.vacancy_title ? ` · ${hr.vacancy_title}` : ""}
                                    </span>
                                  ))}
                                  {/* Каталожные метки + «+». Тот же компонент, что
                                      в «Все кандидаты» — раньше этот блок был только
                                      здесь, отчего в общей базе метку поставить было
                                      нельзя. entityTags держим у себя: ниже он идёт
                                      в данные для AI-панели. */}
                                  <TagPicker
                                    entityId={selectedCandidate?.entity_id}
                                    onChange={setEntityTags}
                                    disabled={hlReadonly}
                                  />
                                </div>
                              </div>
                                </div>
                                {(selectedCandidate as { entity_photo?: string }).entity_photo ? (
                                  <img
                                    src={(selectedCandidate as { entity_photo?: string }).entity_photo}
                                    alt={selectedCandidate.entity_name || ''}
                                    referrerPolicy="no-referrer"
                                    className="hf-profile-photo"
                                  />
                                ) : (
                                  <div className="hf-profile-photo hf-profile-photo-fallback">
                                    {getCandidateFallbackInitial(selectedCandidate.entity_name)}
                                  </div>
                                )}
                              </div>

                              {/* Вакансии и история — та же богатая карточка, что и в
                                  «Все кандидаты» (CandidateVacancyCard), по контейнеру
                                  стека (живой + merged_from) через buildStageContainers. */}
                              <div className="px-5 pt-4 flex flex-col gap-3">
                                <div className="text-sm font-medium text-[var(--hf-dark-400)] mb-1">Вакансии и история</div>
                                {entityActivity.length === 0 || !funnelCard ? (
                                  <div className="text-sm text-[var(--hf-dark-600)]">Нет участий в вакансиях</div>
                                ) : (
                                  containers.map((c) => (
                                    <CandidateVacancyCard
                                      key={`${c.origin}-${c.applicationId}`}
                                      card={funnelCard}
                                      applicationId={c.applicationId}
                                      vacancyTitle={c.vacancyTitle}
                                      currentStage={c.status}
                                      notes={c.notes}
                                      events={c.events}
                                      addedAt={c.addedAt}
                                      /* Архивная (закрытая) вакансия — карточка визуально
                                         read-only, как merged: не должна выглядеть
                                         активной, если менять всё равно нельзя. */
                                      readonly={c.origin === 'merged' || vacancyArchived || hlReadonly}
                                      /* Наблюдатель: карточка цветная и лента полная,
                                         только без кнопок (dimmed/snapshot — нет). */
                                      dimmed={c.origin === 'merged' || vacancyArchived}
                                      snapshot={c.origin === 'merged'}
                                      /* Серая карточка этапа — только живой контейнер
                                         и только пока отклик в «предыдущих сериях». */
                                      isPreviousSeries={c.origin === 'live' && !!selectedCandidate?.is_previous_series}
                                      stageOptions={stagePickerOptions}
                                      getStageLabel={getVacancyStageLabel}
                                      onChangeStage={cardChangeStage}
                                      onComment={cardActions.comment}
                                      onDeleteHistory={cardActions.deleteHistory}
                                      onEditHistory={cardActions.editHistory}
                                      onPin={cardActions.pin}
                                      pinnedEntryKey={c.pinnedEntryKey}
                                      onDeleteNote={cardActions.deleteNote}
                                      onEditNote={cardActions.editNote}
                                      onUploadFile={cardActions.uploadFile}
                                      onAnketa={c.origin === 'live' && !vacancyArchived ? () => {
                                        if (!selectedCandidate.entity_id) return;
                                        setAnketaTarget({ id: selectedCandidate.entity_id, name: selectedCandidate.entity_name || '' });
                                        setAnketaOpen(true);
                                      } : undefined}
                                      anketaCount={anketaCount}
                                      onReact={c.origin === 'live' ? cardActions.react : undefined}
                                      files={c.files}
                                      onDeleteFile={c.origin === 'live' && !vacancyArchived && !hlReadonly ? cardActions.deleteFile : undefined}
                                    />
                                  ))
                                )}
                              </div>

                              {/* Ряд вкладок под карточкой — паритет с «Все
                                  кандидаты»: «Анкеты» (с бейджем непрочитанных) +
                                  «Резюме». Вкладки «Личные заметки» больше нет —
                                  заметки пишутся в композере карточки (cardActions.comment)
                                  и показываются в её ленте. */}
                              <div className="hf-vacancy-detail-tabs">
                                <button
                                  type="button"
                                  onClick={() => setDetailTab('anketa')}
                                  className={clsx(
                                    'hf-vacancy-detail-tab',
                                    detailTab === 'anketa' && 'hf-vacancy-detail-tab-active',
                                  )}
                                >
                                  Анкеты
                                  {anketaCount > 0 && (
                                    <span className="ml-1 inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full bg-[#e11d48] text-white text-[11px] leading-none align-middle">
                                      {anketaCount > 9 ? '9+' : anketaCount}
                                    </span>
                                  )}
                                </button>
                                {/* По одной вкладке «Резюме» на источник (паритет с
                                    «Все кандидаты»). */}
                                {(resumeSources.length > 0 ? resumeSources : [null]).map((_s, i) => (
                                  <button
                                    key={i}
                                    type="button"
                                    onClick={() => { setDetailTab('resume'); setResumeIndex(i); }}
                                    className="hf-vacancy-detail-tab"
                                  >
                                    <FileText className="h-[14px] w-[14px]" />
                                    Резюме
                                  </button>
                                ))}
                              </div>

                              {detailTab === 'anketa' && selectedCandidate.entity_id && (
                                <div className="hf-vacancy-notes-panel">
                                  <FunnelAnketaTab entityId={selectedCandidate.entity_id} />
                                </div>
                              )}
                              {/* Резюме — нижняя секция профиля (паритет с «Все
                                  кандидаты»): инфо и история остаются выше, резюме
                                  показывается под ними, а не отдельной страницей. */}
                              {detailTab === 'resume' && (
                                <div className="mt-4">
                                  {filesLoading ? (
                                    <div className="flex items-center justify-center py-16">
                                      <Loader2 className="w-6 h-6 animate-spin text-[var(--hf-accent)]" />
                                    </div>
                                  ) : !hasResume ? (
                                    <div className="flex flex-col items-center justify-center py-16 text-center">
                                      <FileText className="w-12 h-12 text-[var(--hf-dark-600)] mb-3" />
                                      <p className="text-sm text-[var(--hf-dark-400)]">Нет загруженных резюме</p>
                                      <p className="text-xs text-[var(--hf-dark-500)] mt-1">
                                        Загрузите PDF-резюме в профиле кандидата
                                      </p>
                                    </div>
                                  ) : funnelCard ? (
                                    <ResumeTab card={funnelCard} activeIndex={resumeIndex} />
                                  ) : null}
                                </div>
                              )}
                            </div>
                        </div>

                        {/* Дровер «Анкета» — отправка/привязка анкеты живому
                            контейнеру (открывается чипом на карточке). */}
                        {anketaOpen && anketaTarget && (
                          <Suspense fallback={null}>
                            <AnketaDrawer
                              open={anketaOpen}
                              onOpenChange={setAnketaOpen}
                              entityId={anketaTarget.id}
                              entityName={anketaTarget.name}
                              vacancyId={selectedVacancyId ?? undefined}
                              vacancyTitle={selectedVacancy?.title}
                            />
                          </Suspense>
                        )}
                      </>
                    ) : (
                      <div className="hf-vacancy-no-selection flex-1 flex items-center justify-center h-full text-[var(--hf-dark-500)]">
                        <div className="text-center">
                          <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
                          <p className="text-sm">Выберите кандидата из списка</p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
                )}
              </>
            )}
          </div>
        )}
      </main>

      {/* «Перенос кандидатов» — уходящий рекрутёр X → живой Y (админ/суперадмин). */}
      {showHandover && (
        <CandidateHandoverModal
          onClose={() => setShowHandover(false)}
          onDone={() => fetchVacancies()}
        />
      )}

      {/* Create / Edit Vacancy Modal — единая VacancyForm */}
      {showCreateModal && (
        <VacancyForm
          key="create-funnel"
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => { setShowCreateModal(false); fetchVacancies(); }}
        />
      )}

      {editingVacancy && (
        <VacancyForm
          key={`edit-${editingVacancy.id}`}
          vacancy={editingVacancy}
          onClose={() => setEditingVacancy(null)}
          onSuccess={() => {
            const reopenedId = editingVacancy.id;
            setEditingVacancy(null);
            fetchVacancies();
            // Тот же кандидат мог быть открыт в «предыдущей серии» — без
            // перезагрузки списка её этап/зелёный статус не обновится наверху
            // до ручного F5 (см. handleReopenVacancy).
            if (reopenedId === selectedVacancyId) loadCandidates(reopenedId);
          }}
        />
      )}

      {editingCandidateCard && (
        <EditCandidateModal
          card={editingCandidateCard}
          onClose={() => setEditingCandidateCard(null)}
          onSaved={handleCandidateSaved}
          onDeleted={() => {
            setCandidates((items) => items.filter((c) => c.entity_id !== editingCandidateCard?.id));
            setEditingCandidateCard(null);
          }}
        />
      )}

      {/* Confirm modal — close / leave / delete vacancy */}
      {confirmDialog && (
        <VacancyConfirmModal
          action={confirmDialog.type}
          vacancy={confirmDialog.vacancy}
          userId={user?.id}
          busy={confirmBusy}
          onCancel={() => setConfirmDialog(null)}
          onConfirm={runConfirmedAction}
        />
      )}

    </div>
  );
}

/* StageDropdown удалён — на воронке смена этапа теперь через богатый пикер
   (список этапов + «Записать комментарий») прямо в карточке кандидата. */

// Вкладка «Анкеты» в воронке: тянет диспатчи анкет по кандидату, разово
// помечает прочитанными + гасит бейдж, поллит раз в 15с (на проде realtime по
// WS может не доходить). Источник тот же, что у «Все кандидаты»
// (all-dispatches): до 20.10.2026 воронка брала урезанную копию — без ссылок на
// файлы из ответов и без анкет влитых дублей.
function FunnelAnketaTab({ entityId }: { entityId: number }) {
  const [dispatches, setDispatches] = useState<(FormDispatchInfo & { source_entity_id?: number; source_name?: string | null })[]>([]);
  const clearBadge = useFormBadgeStore((s) => s.clear);
  useEffect(() => {
    let alive = true;
    const fetchRows = async () => {
      try {
        const rows = await getEntityAllDispatches(entityId);
        if (alive) setDispatches(rows);
      } catch {
        /* пустой/ошибка — покажем пустое состояние */
      }
    };
    (async () => {
      await fetchRows();
      try { await markEntityDispatchesSeen(entityId); clearBadge(entityId); } catch { /* ignore */ }
    })();
    const t = setInterval(fetchRows, 15000);
    return () => { alive = false; clearInterval(t); };
  }, [entityId, clearBadge]);
  return (
    <AnketaResponses
      dispatches={dispatches}
      onDeleted={(id) => setDispatches((prev) => prev.filter((d) => d.id !== id))}
    />
  );
}
