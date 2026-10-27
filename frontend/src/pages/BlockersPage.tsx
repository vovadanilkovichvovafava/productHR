import { useState, useEffect, useCallback } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  MessageSquare,
  ChevronDown,
  Send,
} from 'lucide-react';
import clsx from 'clsx';
import * as blockersApi from '@/services/api/blockers';
import type { Blocker } from '@/services/api/blockers';

// ============================================================
// CONSTANTS
// ============================================================

const FILTERS = [
  { value: 'open', label: 'Открытые' },
  { value: 'resolved', label: 'Решённые' },
  { value: '', label: 'Все' },
];

// ============================================================
// HELPERS
// ============================================================

function timeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'только что';
  if (diffMin < 60) return `${diffMin} мин назад`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH} ч назад`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return `${diffD} дн назад`;
  return new Date(dateStr).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
  });
}

// ============================================================
// BLOCKER CARD COMPONENT
// ============================================================

function BlockerCard({
  blocker,
  onResolve,
  isResolving,
}: {
  blocker: Blocker;
  onResolve: (id: number, comment: string) => void;
  isResolving: boolean;
}) {
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState('');
  const isOpen = blocker.status === 'open';

  return (
    <div
      className={clsx(
        'bg-white/[0.02] border rounded-xl p-4 transition-colors',
        isOpen
          ? 'border-l-4 border-l-red-500 border-t-white/[0.08] border-r-white/[0.08] border-b-white/[0.08]'
          : 'border-white/[0.06] opacity-60'
      )}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <div
            className={clsx(
              'w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 border',
              isOpen
                ? 'bg-red-500/15 border-red-500/20'
                : 'bg-emerald-500/15 border-emerald-500/20'
            )}
          >
            <span className="text-[10px] font-medium text-white/60">
              {blocker.user_name?.[0]?.toUpperCase() || '?'}
            </span>
          </div>
          <div className="min-w-0">
            <span className="text-sm font-medium text-white">
              {blocker.user_name || 'Без имени'}
            </span>
            <span className="text-[10px] text-white/20 ml-2">{timeAgo(blocker.created_at)}</span>
          </div>
        </div>

        {isOpen && (
          <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-red-500/15 text-red-400 flex-shrink-0">
            <AlertTriangle className="w-3 h-3" />
            Открыт
          </span>
        )}
        {!isOpen && (
          <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/15 text-emerald-400 flex-shrink-0">
            <CheckCircle2 className="w-3 h-3" />
            Решён
          </span>
        )}
      </div>

      {/* Description */}
      <p className="text-sm text-white/70 leading-relaxed mb-3 pl-9">{blocker.description}</p>

      {/* Resolution info */}
      {!isOpen && blocker.resolved_at && (
        <div className="pl-9 mb-2">
          <div className="flex items-center gap-2 text-[11px] text-white/25">
            <CheckCircle2 className="w-3 h-3 text-emerald-400/50" />
            <span>
              Решил {blocker.resolver_name || '—'} {timeAgo(blocker.resolved_at)}
            </span>
          </div>
          {blocker.resolve_comment && (
            <p className="text-[11px] text-white/30 mt-1 pl-5 italic">
              {blocker.resolve_comment}
            </p>
          )}
        </div>
      )}

      {/* Action buttons for open blockers */}
      {isOpen && (
        <div className="pl-9">
          {!showComment ? (
            <button
              onClick={() => setShowComment(true)}
              disabled={isResolving}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition-colors text-[11px] font-medium"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              Решить
            </button>
          ) : (
            <div className="flex items-center gap-2 mt-1">
              <div className="relative flex-1">
                <MessageSquare className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/20" />
                <input
                  type="text"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      onResolve(blocker.id, comment);
                      setComment('');
                      setShowComment(false);
                    }
                    if (e.key === 'Escape') {
                      setShowComment(false);
                      setComment('');
                    }
                  }}
                  placeholder="Комментарий (необязательно)..."
                  className="w-full bg-white/[0.05] border border-white/10 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-white/20 focus:outline-none focus:border-emerald-500/40"
                  autoFocus
                />
              </div>
              <button
                onClick={() => {
                  onResolve(blocker.id, comment);
                  setComment('');
                  setShowComment(false);
                }}
                disabled={isResolving}
                className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
              >
                {isResolving ? (
                  <div className="animate-spin w-3.5 h-3.5 border-2 border-emerald-400/30 border-t-emerald-400 rounded-full" />
                ) : (
                  <Send className="w-3.5 h-3.5" />
                )}
              </button>
              <button
                onClick={() => {
                  setShowComment(false);
                  setComment('');
                }}
                className="text-[10px] text-white/30 hover:text-white/50 transition-colors"
              >
                Отмена
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================
// MAIN PAGE
// ============================================================

export default function BlockersPage() {
  const [blockers, setBlockers] = useState<Blocker[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('open');
  const [resolvingId, setResolvingId] = useState<number | null>(null);
  const [showResolved, setShowResolved] = useState(false);

  const fetchBlockers = useCallback(async () => {
    setLoading(true);
    try {
      const data = await blockersApi.getBlockers(filter || undefined);
      setBlockers(data);
    } catch {
      setBlockers([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    fetchBlockers();
  }, [fetchBlockers]);

  const handleResolve = async (id: number, comment: string) => {
    setResolvingId(id);
    try {
      await blockersApi.resolveBlocker(id, comment || undefined);
      await fetchBlockers();
    } catch {
      // silently ignore
    } finally {
      setResolvingId(null);
    }
  };

  const openBlockers = blockers.filter((b) => b.status === 'open');
  const resolvedBlockers = blockers.filter((b) => b.status === 'resolved');

  // When filter is empty (Все), show both sections; otherwise show filtered
  const showOpenSection = filter === '' || filter === 'open';
  const showResolvedSection = filter === '' || filter === 'resolved';

  return (
    <div className="min-h-screen p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-red-500/10 border border-red-500/20">
            <AlertTriangle className="w-5 h-5 text-red-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">Блокеры</h1>
            <p className="text-[11px] text-white/30">Проблемы, блокирующие работу команды</p>
          </div>
        </div>

        {/* Stats badges */}
        {!loading && (
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400 font-medium">
              <AlertTriangle className="w-3 h-3" />
              {openBlockers.length} открыт{openBlockers.length === 1 ? '' : 'о'}
            </span>
            <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-400 font-medium">
              <CheckCircle2 className="w-3 h-3" />
              {resolvedBlockers.length} решен{resolvedBlockers.length === 1 ? '' : 'о'}
            </span>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 mb-4">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={clsx(
              'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
              filter === f.value
                ? 'bg-white/10 text-white'
                : 'text-white/30 hover:text-white/50 bg-white/[0.02]'
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin w-8 h-8 border-2 border-red-400 border-t-transparent rounded-full" />
        </div>
      )}

      {/* Empty */}
      {!loading && blockers.length === 0 && (
        <div className="flex flex-col items-center py-16 text-center">
          <AlertTriangle className="w-10 h-10 text-white/10 mb-3" />
          <p className="text-sm text-white/30">Нет блокеров</p>
          <p className="text-xs text-white/15 mt-1">
            {filter === 'open'
              ? 'Все проблемы решены'
              : filter === 'resolved'
                ? 'Нет решённых блокеров'
                : 'Блокеры появятся здесь'}
          </p>
        </div>
      )}

      {/* Open blockers */}
      {!loading && showOpenSection && openBlockers.length > 0 && (
        <div className="mb-6">
          {filter === '' && (
            <h2 className="text-xs font-semibold uppercase tracking-wider text-red-400/60 mb-3">
              Открытые ({openBlockers.length})
            </h2>
          )}
          <div className="space-y-3">
            {openBlockers.map((blocker) => (
              <BlockerCard
                key={blocker.id}
                blocker={blocker}
                onResolve={handleResolve}
                isResolving={resolvingId === blocker.id}
              />
            ))}
          </div>
        </div>
      )}

      {/* Resolved blockers (collapsible when filter is "all") */}
      {!loading && showResolvedSection && resolvedBlockers.length > 0 && (
        <div>
          {filter === '' ? (
            <>
              <button
                onClick={() => setShowResolved(!showResolved)}
                className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-emerald-400/60 mb-3 hover:text-emerald-400/80 transition-colors"
              >
                <ChevronDown
                  className={clsx(
                    'w-3.5 h-3.5 transition-transform',
                    !showResolved && '-rotate-90'
                  )}
                />
                Решённые ({resolvedBlockers.length})
              </button>
              {showResolved && (
                <div className="space-y-3">
                  {resolvedBlockers.map((blocker) => (
                    <BlockerCard
                      key={blocker.id}
                      blocker={blocker}
                      onResolve={handleResolve}
                      isResolving={resolvingId === blocker.id}
                    />
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="space-y-3">
              {resolvedBlockers.map((blocker) => (
                <BlockerCard
                  key={blocker.id}
                  blocker={blocker}
                  onResolve={handleResolve}
                  isResolving={resolvingId === blocker.id}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
