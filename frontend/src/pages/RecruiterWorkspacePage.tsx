import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import {
  ChevronDown, ChevronRight, Briefcase, Plus,
  Search, LayoutList, Columns3, FolderOpen,
} from 'lucide-react';
import clsx from 'clsx';
import * as workspacesApi from '@/services/api/workspaces';
import { smartNameMatch, contactMatch } from '@/utils/translit';
import { FUNNEL_STAGE_ORDER, HR_STAGES, STAGE_LABEL_BY_STAGE, STAGE_TAB_COLORS, type StageTabColors } from '@/constants/hrStages';

// --------------- constants ---------------

// Порядок, подписи и цвета этапов — общий справочник (constants/hrStages.ts).
// Раньше тут была своя копия без «Практики», «Перешёл в отдел» и «Резерва»:
// такие кандидаты уезжали в конец списка серыми.
const STAGE_ORDER = FUNNEL_STAGE_ORDER;
const STAGE_LABELS: Record<string, string> = STAGE_LABEL_BY_STAGE;
const STAGE_COLORS = Object.fromEntries(
  HR_STAGES.map((st) => [st.stage, STAGE_TAB_COLORS[st.color]]),
) as Record<string, StageTabColors>;

const fallbackColor = { bg: 'bg-[var(--hf-white-alpha-10)]', text: 'text-[var(--hf-dark-300)]', dot: 'bg-[var(--hf-dark-400)]', badge: 'bg-[var(--hf-white-alpha-15)] text-[var(--hf-dark-300)]' };

// --------------- types ---------------

interface SidebarVacancy {
  id: number;
  title: string;
  status: string;
  candidate_count: number;
}

interface SidebarSpace {
  recruiterId: number;
  name: string;
  email: string;
  vacancies: SidebarVacancy[];
  expanded: boolean;
}

interface CandidateRow {
  id: number;
  name: string;
  email?: string | null;
  phone?: string | null;
  telegram?: string | null;
  stage: string;
  stage_label: string;
  applied_at?: string | null;
  source?: string | null;
  vacancy_title: string;
  vacancy_id: number;
}

// --------------- component ---------------

export default function RecruiterWorkspacePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuthStore();

  const isAdmin = user?.role === 'superadmin' || user?.org_role === 'owner' || user?.org_role === 'admin';

  // sidebar state
  const [spaces, setSpaces] = useState<SidebarSpace[]>([]);
  const [sidebarLoading, setSidebarLoading] = useState(true);

  // selected funnel
  const selectedVacancyId = searchParams.get('v') ? Number(searchParams.get('v')) : null;
  const selectedRecruiterId = searchParams.get('r') ? Number(searchParams.get('r')) : null;

  // main content
  const [candidates, setCandidates] = useState<CandidateRow[]>([]);
  const [contentLoading, setContentLoading] = useState(false);
  const [view, setView] = useState<'list' | 'board'>('list');
  const [searchQuery, setSearchQuery] = useState('');
  const [collapsedStages, setCollapsedStages] = useState<Set<string>>(new Set());

  // --------------- sidebar data ---------------

  useEffect(() => {
    loadSidebar();
  }, []);

  const loadSidebar = useCallback(async () => {
    setSidebarLoading(true);
    try {
      const summaries = await workspacesApi.getWorkspaces();
      const spacesData: SidebarSpace[] = [];

      for (const ws of summaries) {
        const detail = await workspacesApi.getWorkspace(ws.recruiter_id);
        spacesData.push({
          recruiterId: ws.recruiter_id,
          name: ws.name,
          email: ws.email,
          vacancies: detail.vacancies.map((v) => ({
            id: v.id,
            title: v.title,
            status: v.status,
            candidate_count: v.candidate_count,
          })),
          // auto-expand for non-admin (single space) or first space for admin
          expanded: !isAdmin || spacesData.length === 0,
        });
      }

      // For non-admin: auto-expand their only space
      if (!isAdmin && spacesData.length === 1) {
        spacesData[0].expanded = true;
      }

      setSpaces(spacesData);

      // auto-select first vacancy if nothing selected
      if (!selectedVacancyId && spacesData.length > 0) {
        const firstSpace = spacesData.find((s) => s.vacancies.length > 0);
        if (firstSpace) {
          firstSpace.expanded = true;
          const v = firstSpace.vacancies[0];
          setSearchParams({ r: String(firstSpace.recruiterId), v: String(v.id) });
        }
      }
    } catch {
      // silent
    } finally {
      setSidebarLoading(false);
    }
  }, [isAdmin]);

  // --------------- load candidates for selected vacancy ---------------

  useEffect(() => {
    if (!selectedVacancyId || !selectedRecruiterId) {
      setCandidates([]);
      return;
    }
    loadCandidates(selectedRecruiterId, selectedVacancyId);
  }, [selectedVacancyId, selectedRecruiterId]);

  const loadCandidates = useCallback(async (recruiterId: number, vacancyId: number) => {
    setContentLoading(true);
    try {
      const res = await workspacesApi.getWorkspaceCandidates(recruiterId, {
        vacancy_id: vacancyId,
        limit: 200,
      });
      setCandidates(res.items);
    } catch {
      setCandidates([]);
    } finally {
      setContentLoading(false);
    }
  }, []);

  // --------------- derived data ---------------

  const selectedSpace = useMemo(
    () => spaces.find((s) => s.recruiterId === selectedRecruiterId),
    [spaces, selectedRecruiterId],
  );

  const selectedVacancy = useMemo(
    () => selectedSpace?.vacancies.find((v) => v.id === selectedVacancyId),
    [selectedSpace, selectedVacancyId],
  );

  const filteredCandidates = useMemo(() => {
    if (!searchQuery.trim()) return candidates;
    return candidates.filter(
      (c) =>
        smartNameMatch(c.name || '', searchQuery) ||  // транслит + порядок + опечатки + раскладка
        contactMatch(searchQuery, { email: c.email, phone: c.phone, telegram: c.telegram }),
    );
  }, [candidates, searchQuery]);

  const groupedByStage = useMemo(() => {
    const map = new Map<string, CandidateRow[]>();
    for (const stage of STAGE_ORDER) map.set(stage, []);
    for (const c of filteredCandidates) {
      const arr = map.get(c.stage);
      if (arr) arr.push(c);
      else {
        if (!map.has(c.stage)) map.set(c.stage, []);
        map.get(c.stage)!.push(c);
      }
    }
    // remove empty stages
    const result: [string, CandidateRow[]][] = [];
    for (const [stage, items] of map) {
      if (items.length > 0) result.push([stage, items]);
    }
    return result;
  }, [filteredCandidates]);

  // --------------- handlers ---------------

  const toggleSpace = (recruiterId: number) => {
    setSpaces((prev) =>
      prev.map((s) =>
        s.recruiterId === recruiterId ? { ...s, expanded: !s.expanded } : s,
      ),
    );
  };

  const selectVacancy = (recruiterId: number, vacancyId: number) => {
    setSearchParams({ r: String(recruiterId), v: String(vacancyId) });
    setSearchQuery('');
    setCollapsedStages(new Set());
  };

  const toggleStage = (stage: string) => {
    setCollapsedStages((prev) => {
      const next = new Set(prev);
      if (next.has(stage)) next.delete(stage);
      else next.add(stage);
      return next;
    });
  };

  const formatDate = (iso?: string | null) => {
    if (!iso) return '';
    try {
      return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' });
    } catch {
      return '';
    }
  };

  // --------------- render ---------------

  return (
    <div className="h-full flex overflow-hidden">
      {/* ========== LEFT SIDEBAR ========== */}
      <aside className="w-[260px] flex-shrink-0 border-r border-[color:var(--hf-white-alpha-06)] bg-[var(--hf-white-alpha-02)] flex flex-col overflow-hidden">
        {/* Sidebar header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[color:var(--hf-white-alpha-06)]">
          <span className="text-xs font-semibold text-[var(--hf-dark-400)] uppercase tracking-wider">Spaces</span>
          <button className="p-1 hover:bg-[var(--hf-white-alpha-06)] rounded transition-colors" title="Добавить">
            <Plus className="w-3.5 h-3.5 text-[var(--hf-dark-400)]" />
          </button>
        </div>

        {/* Sidebar tree */}
        <div className="flex-1 overflow-y-auto py-1">
          {sidebarLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-5 h-5 border-2 border-[var(--hf-accent)] border-t-transparent rounded-full animate-spin" />
            </div>
          ) : spaces.length === 0 ? (
            <div className="px-4 py-8 text-center text-[var(--hf-dark-500)] text-xs">
              Нет рекрутеров
            </div>
          ) : (
            spaces.map((space) => (
              <div key={space.recruiterId}>
                {/* Space (folder) header */}
                <button
                  onClick={() => toggleSpace(space.recruiterId)}
                  className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-[var(--hf-white-alpha-04)] transition-colors group"
                >
                  {space.expanded ? (
                    <ChevronDown className="w-3.5 h-3.5 text-[var(--hf-dark-500)] flex-shrink-0" />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5 text-[var(--hf-dark-500)] flex-shrink-0" />
                  )}
                  <FolderOpen className="w-4 h-4 text-[var(--hf-status-purple)] flex-shrink-0" />
                  <span className="text-sm text-[var(--hf-dark-200)] truncate flex-1 text-left font-medium">
                    {space.name}
                  </span>
                  <span className="text-[10px] text-[var(--hf-dark-500)] flex-shrink-0">
                    {space.vacancies.length}
                  </span>
                </button>

                {/* Vacancy list inside space */}
                {space.expanded && (
                  <div className="ml-3">
                    {space.vacancies.length === 0 ? (
                      <div className="px-6 py-2 text-xs text-[var(--hf-dark-500)]">Нет воронок</div>
                    ) : (
                      space.vacancies.map((v) => {
                        const isSelected = selectedVacancyId === v.id && selectedRecruiterId === space.recruiterId;
                        return (
                          <button
                            key={v.id}
                            onClick={() => selectVacancy(space.recruiterId, v.id)}
                            className={clsx(
                              'w-full flex items-center gap-2 pl-6 pr-3 py-1.5 text-left transition-colors',
                              isSelected
                                ? 'bg-[var(--hf-accent-bg-10)] text-[var(--hf-accent)]'
                                : 'hover:bg-[var(--hf-white-alpha-04)] text-[var(--hf-dark-300)]',
                            )}
                          >
                            <Briefcase className="w-3.5 h-3.5 flex-shrink-0 opacity-60" />
                            <span className="text-sm truncate flex-1">{v.title}</span>
                            <span className={clsx(
                              'text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0',
                              isSelected ? 'bg-[var(--hf-accent-bg-20)] text-[var(--hf-accent)]' : 'bg-[var(--hf-white-alpha-06)] text-[var(--hf-dark-400)]',
                            )}>
                              {v.candidate_count}
                            </span>
                          </button>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </aside>

      {/* ========== MAIN CONTENT ========== */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {!selectedVacancy ? (
          <div className="flex-1 flex flex-col items-center justify-center text-[var(--hf-dark-500)]">
            <Briefcase className="w-12 h-12 mb-3 opacity-30" />
            <p className="text-sm">Выберите воронку в меню слева</p>
          </div>
        ) : (
          <>
            {/* Top bar: breadcrumb + view tabs */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-[color:var(--hf-white-alpha-06)] bg-[var(--hf-white-alpha-02)]">
              {/* Breadcrumb */}
              <div className="flex items-center gap-1.5 text-sm min-w-0">
                <span className="text-[var(--hf-dark-500)]">HR отдел</span>
                <ChevronRight className="w-3.5 h-3.5 text-[var(--hf-dark-600)] flex-shrink-0" />
                <span className="text-[var(--hf-dark-400)] truncate max-w-[180px]">
                  {selectedSpace?.name}
                </span>
                <ChevronRight className="w-3.5 h-3.5 text-[var(--hf-dark-600)] flex-shrink-0" />
                <span className="text-[var(--hf-dark-200)] font-medium truncate max-w-[200px]">
                  {selectedVacancy.title}
                </span>
              </div>

              {/* View tabs + search */}
              <div className="flex items-center gap-3 flex-shrink-0">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--hf-dark-500)]" />
                  <input
                    type="text"
                    placeholder="Поиск..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-44 pl-8 pr-3 py-1.5 bg-[var(--hf-white-alpha-03)] border border-[color:var(--hf-white-alpha-06)] rounded-lg text-xs text-[var(--hf-dark-200)] placeholder:text-[var(--hf-dark-500)] focus:outline-none focus:border-[color:var(--hf-accent-border-40)]"
                  />
                </div>
                <div className="flex items-center bg-[var(--hf-white-alpha-03)] rounded-lg border border-[color:var(--hf-white-alpha-06)] p-0.5">
                  <button
                    onClick={() => setView('list')}
                    className={clsx(
                      'flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-colors',
                      view === 'list' ? 'bg-[var(--hf-accent-bg-15)] text-[var(--hf-accent)]' : 'text-[var(--hf-dark-400)] hover:text-[var(--hf-dark-200)]',
                    )}
                  >
                    <LayoutList className="w-3.5 h-3.5" />
                    Список
                  </button>
                  <button
                    onClick={() => setView('board')}
                    className={clsx(
                      'flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-colors',
                      view === 'board' ? 'bg-[var(--hf-accent-bg-15)] text-[var(--hf-accent)]' : 'text-[var(--hf-dark-400)] hover:text-[var(--hf-dark-200)]',
                    )}
                  >
                    <Columns3 className="w-3.5 h-3.5" />
                    Доска
                  </button>
                </div>
              </div>
            </div>

            {/* Content area */}
            <div className="flex-1 overflow-y-auto">
              {contentLoading ? (
                <div className="flex items-center justify-center py-16">
                  <div className="w-6 h-6 border-2 border-[var(--hf-accent)] border-t-transparent rounded-full animate-spin" />
                </div>
              ) : view === 'list' ? (
                /* ===== LIST VIEW: grouped by stage ===== */
                <div className="px-5 py-3 space-y-1">
                  {groupedByStage.length === 0 ? (
                    <div className="text-center py-16 text-[var(--hf-dark-500)] text-sm">
                      {searchQuery ? 'Ничего не найдено' : 'Нет кандидатов в этой воронке'}
                    </div>
                  ) : (
                    groupedByStage.map(([stage, items]) => {
                      const colors = STAGE_COLORS[stage] || fallbackColor;
                      const collapsed = collapsedStages.has(stage);
                      return (
                        <div key={stage} className="mb-1">
                          {/* Stage group header */}
                          <button
                            onClick={() => toggleStage(stage)}
                            className={clsx(
                              'w-full flex items-center gap-2 px-3 py-2 rounded-lg transition-colors',
                              colors.bg,
                            )}
                          >
                            {collapsed ? (
                              <ChevronRight className={clsx('w-4 h-4', colors.text)} />
                            ) : (
                              <ChevronDown className={clsx('w-4 h-4', colors.text)} />
                            )}
                            <span className={clsx('w-2 h-2 rounded-full', colors.dot)} />
                            <span className={clsx('text-sm font-semibold', colors.text)}>
                              {STAGE_LABELS[stage] || stage}
                            </span>
                            <span className={clsx('text-xs ml-1 opacity-70', colors.text)}>
                              ({items.length})
                            </span>
                          </button>

                          {/* Candidate rows */}
                          {!collapsed && (
                            <div className="mt-0.5">
                              {/* Column headers */}
                              <div className="grid grid-cols-[1fr_120px_100px_140px_120px] gap-2 px-3 py-1.5 text-[11px] text-[var(--hf-dark-500)] font-medium uppercase tracking-wide">
                                <span>Имя</span>
                                <span>Статус</span>
                                <span>Дата</span>
                                <span>Telegram</span>
                                <span>Источник</span>
                              </div>

                              {items.map((c) => (
                                <div
                                  key={`${c.id}-${c.vacancy_id}`}
                                  onClick={() => navigate(`/all-candidates?entity=${c.id}`)}
                                  className="grid grid-cols-[1fr_120px_100px_140px_120px] gap-2 px-3 py-2 hover:bg-[var(--hf-white-alpha-03)] rounded-lg cursor-pointer transition-colors border-b border-[color:var(--hf-white-alpha-03)] last:border-b-0 group"
                                >
                                  {/* Name */}
                                  <div className="flex items-center gap-2 min-w-0">
                                    <div className="w-6 h-6 rounded-full bg-[var(--hf-accent-bg-10)] flex items-center justify-center text-[10px] text-[var(--hf-accent)] font-medium flex-shrink-0">
                                      {c.name.charAt(0).toUpperCase()}
                                    </div>
                                    <span className="text-sm text-[var(--hf-dark-100)] truncate group-hover:text-[var(--hf-accent)] transition-colors">
                                      {c.name}
                                    </span>
                                  </div>
                                  {/* Status badge */}
                                  <div className="flex items-center">
                                    <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium', colors.badge)}>
                                      {c.stage_label}
                                    </span>
                                  </div>
                                  {/* Date */}
                                  <span className="text-xs text-[var(--hf-dark-400)] flex items-center">
                                    {formatDate(c.applied_at)}
                                  </span>
                                  {/* Telegram */}
                                  <span className="text-xs text-[var(--hf-dark-400)] truncate flex items-center">
                                    {c.telegram ? `@${c.telegram}` : ''}
                                  </span>
                                  {/* Source */}
                                  <span className="text-xs text-[var(--hf-dark-400)] truncate flex items-center">
                                    {c.source || ''}
                                  </span>
                                </div>
                              ))}

                              {/* Add candidate row */}
                              <button className="flex items-center gap-2 px-3 py-2 text-xs text-[var(--hf-dark-500)] hover:text-[var(--hf-dark-300)] transition-colors w-full">
                                <Plus className="w-3.5 h-3.5" />
                                <span>Добавить кандидата</span>
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              ) : (
                /* ===== BOARD VIEW (kanban-style columns) ===== */
                <div className="flex gap-3 px-5 py-3 overflow-x-auto h-full">
                  {groupedByStage.length === 0 ? (
                    <div className="flex-1 flex items-center justify-center text-[var(--hf-dark-500)] text-sm">
                      {searchQuery ? 'Ничего не найдено' : 'Нет кандидатов в этой воронке'}
                    </div>
                  ) : (
                    groupedByStage.map(([stage, items]) => {
                      const colors = STAGE_COLORS[stage] || fallbackColor;
                      return (
                        <div
                          key={stage}
                          className="w-[280px] flex-shrink-0 flex flex-col bg-[var(--hf-white-alpha-02)] rounded-xl border border-[color:var(--hf-white-alpha-06)] overflow-hidden"
                        >
                          {/* Column header */}
                          <div className={clsx('flex items-center gap-2 px-3 py-2.5 border-b border-[color:var(--hf-white-alpha-06)]', colors.bg)}>
                            <span className={clsx('w-2 h-2 rounded-full', colors.dot)} />
                            <span className={clsx('text-sm font-semibold', colors.text)}>
                              {STAGE_LABELS[stage] || stage}
                            </span>
                            <span className={clsx('text-xs ml-auto opacity-70', colors.text)}>
                              {items.length}
                            </span>
                          </div>

                          {/* Cards */}
                          <div className="flex-1 overflow-y-auto p-2 space-y-2">
                            {items.map((c) => (
                              <div
                                key={`${c.id}-${c.vacancy_id}`}
                                onClick={() => navigate(`/all-candidates?entity=${c.id}`)}
                                className="glass-card rounded-lg p-3 cursor-pointer hover:border-[color:var(--hf-accent-border-30)] transition-all group"
                              >
                                <div className="flex items-center gap-2 mb-2">
                                  <div className="w-6 h-6 rounded-full bg-[var(--hf-accent-bg-10)] flex items-center justify-center text-[10px] text-[var(--hf-accent)] font-medium flex-shrink-0">
                                    {c.name.charAt(0).toUpperCase()}
                                  </div>
                                  <span className="text-sm text-[var(--hf-dark-100)] truncate group-hover:text-[var(--hf-accent)] transition-colors font-medium">
                                    {c.name}
                                  </span>
                                </div>
                                <div className="flex items-center gap-2 text-[11px] text-[var(--hf-dark-400)]">
                                  {c.telegram && <span>@{c.telegram}</span>}
                                  {c.source && <span className="ml-auto">{c.source}</span>}
                                </div>
                                {c.applied_at && (
                                  <div className="text-[10px] text-[var(--hf-dark-500)] mt-1.5">
                                    {formatDate(c.applied_at)}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>

                          {/* Add candidate button */}
                          <button className="flex items-center gap-1.5 px-3 py-2 text-xs text-[var(--hf-dark-500)] hover:text-[var(--hf-dark-300)] hover:bg-[var(--hf-white-alpha-03)] transition-colors border-t border-[color:var(--hf-white-alpha-06)]">
                            <Plus className="w-3.5 h-3.5" />
                            Добавить
                          </button>
                        </div>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
