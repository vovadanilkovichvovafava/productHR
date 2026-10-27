import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Users,
  Search,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Building2,
  ArrowRight,
  User,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { getEntities, updateEntityStatus, getUsers } from '@/services/api';
import type { Entity, EntityStatus } from '@/types';
import { STATUS_LABELS, STATUS_COLORS } from '@/types';

// Practice-related statuses
const PRACTICE_STATUSES: EntityStatus[] = ['practice', 'tech_practice', 'hired'];

// Tab filters
type PracticeTab = 'practice' | 'in_department' | 'dismissed';

const TABS: { id: PracticeTab; label: string; icon: typeof Clock }[] = [
  { id: 'practice', label: 'На практике', icon: Clock },
  { id: 'in_department', label: 'В отделе', icon: Building2 },
  { id: 'dismissed', label: 'Уволен', icon: AlertTriangle },
];

// Helper: parse date from extra_data or entity fields
function parseDate(val: unknown): Date | null {
  if (!val) return null;
  const d = new Date(String(val));
  return isNaN(d.getTime()) ? null : d;
}

function formatShortDate(val: unknown): string {
  const d = parseDate(val);
  if (!d) return '\u2014';
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
}

// Calculate deadline status
function deadlineStatus(dateVal: unknown): 'ok' | 'warning' | 'overdue' | 'none' {
  const d = parseDate(dateVal);
  if (!d) return 'none';
  const now = new Date();
  const diffDays = Math.floor((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  if (diffDays < 0) return 'overdue';
  if (diffDays < 14) return 'warning';
  return 'ok';
}

// Get extra_data field helper
function extra(entity: Entity, key: string): unknown {
  return entity.extra_data?.[key];
}

export default function PracticeListPage() {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<PracticeTab>('practice');
  const [search, setSearch] = useState('');
  const [usersMap, setUsersMap] = useState<Record<number, string>>({});

  // Load entities with practice-related statuses
  const loadEntities = useCallback(async () => {
    setIsLoading(true);
    try {
      const results = await Promise.all(
        PRACTICE_STATUSES.map((status) =>
          getEntities({ type: 'candidate', status })
        )
      );
      setEntities(results.flat());
    } catch {
      toast.error('Ошибка загрузки данных');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadEntities();
  }, [loadEntities]);

  // Load users for recruiter names
  useEffect(() => {
    getUsers().then((users) => {
      const map: Record<number, string> = {};
      users.forEach((u) => { map[u.id] = u.name; });
      setUsersMap(map);
    }).catch(() => {});
  }, []);

  // Filter entities by tab
  const filtered = useMemo(() => {
    let result = entities;

    // Tab-based filtering
    switch (activeTab) {
      case 'practice':
        result = result.filter(
          (e) => e.status === 'practice' || e.status === 'tech_practice'
        );
        break;
      case 'in_department':
        result = result.filter(
          (e) => e.status === 'hired' && extra(e, 'department_transfer_date')
        );
        break;
      case 'dismissed':
        result = result.filter(
          (e) => extra(e, 'dismissed') === true
        );
        break;
    }

    // Search
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (e) =>
          e.name.toLowerCase().includes(q) ||
          e.position?.toLowerCase().includes(q) ||
          e.department_name?.toLowerCase().includes(q)
      );
    }

    return result;
  }, [entities, activeTab, search]);

  // Handle "Move to department" / "В штат"
  const handleMoveToStaff = async (entity: Entity) => {
    try {
      await updateEntityStatus(entity.id, 'hired');
      toast.success(`${entity.name} переведён в штат`);
      loadEntities();
    } catch {
      toast.error('Ошибка при переводе в штат');
    }
  };

  // Calculate probation end date (3 months from practice start)
  const probationEnd = (entity: Entity): string => {
    const start = parseDate(extra(entity, 'practice_start_date') || entity.created_at);
    if (!start) return '\u2014';
    const end = new Date(start);
    end.setMonth(end.getMonth() + 3);
    return formatShortDate(end.toISOString());
  };

  const tabCounts = useMemo(() => {
    const practice = entities.filter(
      (e) => e.status === 'practice' || e.status === 'tech_practice'
    ).length;
    const inDept = entities.filter(
      (e) => e.status === 'hired' && extra(e, 'department_transfer_date')
    ).length;
    const dismissed = entities.filter(
      (e) => extra(e, 'dismissed') === true
    ).length;
    return { practice, in_department: inDept, dismissed };
  }, [entities]);

  return (
    <div className="h-full flex flex-col gap-4 p-4 lg:p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl lg:text-2xl font-bold text-white">Лист практики</h1>
          <p className="text-sm text-dark-400 mt-0.5">
            {entities.length} человек в системе
          </p>
        </div>
      </div>

      {/* Tabs and search */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        <div className="flex items-center gap-1 bg-dark-800/50 rounded-xl p-1 border border-white/5">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const count = tabCounts[tab.id];
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors',
                  activeTab === tab.id
                    ? 'bg-accent-500/20 text-accent-400'
                    : 'text-dark-400 hover:text-white/70'
                )}
              >
                <Icon className="w-3.5 h-3.5" />
                {tab.label}
                {count > 0 && (
                  <span className={clsx(
                    'px-1.5 py-0.5 text-[10px] rounded-md',
                    activeTab === tab.id ? 'bg-accent-500/30' : 'bg-dark-700'
                  )}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-400" />
          <input
            type="text"
            placeholder="Поиск по ФИО, должности..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-dark-800/50 border border-white/10 rounded-xl text-sm text-white placeholder-dark-400 focus:outline-none focus:border-accent-500/50"
          />
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <div className="w-16 h-16 rounded-2xl bg-dark-800/50 flex items-center justify-center">
              <Users className="w-8 h-8 text-dark-500" />
            </div>
            <p className="text-dark-400 text-sm">Нет записей</p>
          </div>
        ) : (
          <div className="border border-white/[0.06] bg-white/[0.02] rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/5">
                  <th className="text-left px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider">ФИО</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider">Рекрутер</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider">Должность</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider">Отдел</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider">Начало</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider">Испыт. 3 мес</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider">Статус</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {filtered.map((entity) => {
                  const practiceStart = extra(entity, 'practice_start_date') || entity.created_at;
                  const probEnd = probationEnd(entity);
                  const probStatus = deadlineStatus(
                    (() => {
                      const start = parseDate(extra(entity, 'practice_start_date') || entity.created_at);
                      if (!start) return null;
                      const end = new Date(start);
                      end.setMonth(end.getMonth() + 3);
                      return end.toISOString();
                    })()
                  );
                  const recruiterName = entity.owner_id ? (usersMap[entity.owner_id] || entity.owner_name || '\u2014') : '\u2014';

                  return (
                    <tr key={entity.id} className="hover:bg-white/[0.02] transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-lg bg-accent-500/20 flex items-center justify-center shrink-0">
                            <User className="w-3.5 h-3.5 text-accent-400" />
                          </div>
                          <span className="text-white font-medium truncate max-w-[180px]">{entity.name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-dark-300">{recruiterName}</td>
                      <td className="px-4 py-3 text-dark-300">{entity.position || '\u2014'}</td>
                      <td className="px-4 py-3 text-dark-300">{entity.department_name || '\u2014'}</td>
                      <td className="px-4 py-3 text-dark-300 whitespace-nowrap">{formatShortDate(practiceStart)}</td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className={clsx(
                          'inline-flex items-center gap-1',
                          probStatus === 'overdue' && 'text-red-400',
                          probStatus === 'warning' && 'text-yellow-400',
                          probStatus === 'ok' && 'text-dark-300',
                          probStatus === 'none' && 'text-dark-500',
                        )}>
                          {probEnd}
                          {probStatus === 'overdue' && <AlertTriangle className="w-3 h-3" />}
                          {probStatus === 'warning' && <Clock className="w-3 h-3" />}
                          {probStatus === 'ok' && <CheckCircle2 className="w-3 h-3" />}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={clsx(
                          'inline-flex px-2 py-0.5 text-xs font-medium rounded-md border',
                          STATUS_COLORS[entity.status] || 'bg-dark-700 text-dark-300'
                        )}>
                          {STATUS_LABELS[entity.status] || entity.status}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {(entity.status === 'practice' || entity.status === 'tech_practice') && (
                          <button
                            onClick={() => handleMoveToStaff(entity)}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/30 border border-green-500/30 transition-colors"
                          >
                            В штат
                            <ArrowRight className="w-3 h-3" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
