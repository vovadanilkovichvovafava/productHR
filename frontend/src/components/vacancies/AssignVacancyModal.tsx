import { useEffect, useState } from 'react';
import { X, UserPlus } from 'lucide-react';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import { backdropClose } from '@/utils/backdropClose';
import { assignVacancy, getAssignableUsers } from '@/services/api';
import type { AssignableUser } from '@/services/api';
import type { Vacancy } from '@/types';

// Окно «Назначить рекрутеров» для заявки (вынесено из VacanciesPage, 20.10.2026).
export default function AssignVacancyModal({
  vacancy,
  onClose,
  onAssigned,
}: {
  vacancy: Vacancy;
  onClose: () => void;
  onAssigned: () => void;
}) {
  const [users, setUsers] = useState<AssignableUser[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>(vacancy.assigned_to || []);
  const [assignAll, setAssignAll] = useState(vacancy.assigned_to_all || false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getAssignableUsers().then(setUsers).catch(() => toast.error('Не удалось загрузить пользователей'));
  }, []);

  const handleSave = async () => {
    setLoading(true);
    try {
      await assignVacancy(vacancy.id, selectedIds, assignAll);
      toast.success('Заявка назначена');
      onAssigned();
    } catch {
      toast.error('Не удалось назначить заявку');
    } finally {
      setLoading(false);
    }
  };

  const toggleUser = (id: number) => {
    setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--hf-black-alpha-60)]" {...backdropClose(onClose)}>
      <div
        className="w-full max-w-md mx-4 bg-[var(--hf-white)] border border-[var(--hf-ui-border)] text-[var(--hf-main-900)] rounded-2xl shadow-[var(--hf-shadow-2xl)] overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--hf-ui-divider)]">
          <h3 className="text-lg font-semibold">Назначить рекрутеров</h3>
          <button onClick={onClose} className="p-1 rounded-lg text-[var(--hf-main-500)] hover:bg-[var(--hf-ui-hover)] hover:text-[var(--hf-main-900)] transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-4 max-h-96 overflow-y-auto">
          {/* Assign to all toggle */}
          <label className="flex items-center gap-3 p-3 rounded-xl bg-[var(--hf-bg-muted)] border border-[var(--hf-ui-divider)] cursor-pointer hover:bg-[var(--hf-ui-hover)] transition-colors">
            <input
              type="checkbox"
              checked={assignAll}
              onChange={() => setAssignAll(!assignAll)}
              className="w-4 h-4 rounded border-[var(--hf-ui-border)] text-[var(--hf-cyan-700)] focus:ring-[var(--hf-cyan-500)]"
            />
            <div>
              <span className="text-sm font-medium">Назначить всем</span>
              <p className="text-xs text-[var(--hf-main-500)]">Все рекрутеры увидят эту заявку</p>
            </div>
          </label>

          {/* User list */}
          {!assignAll && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-[var(--hf-main-500)] mb-2">Выберите рекрутеров:</p>
              {users.length === 0 ? (
                <div className="flex items-center justify-center py-6">
                  <div className="animate-spin w-5 h-5 border-2 border-[color:var(--hf-status-blue)] border-t-transparent rounded-full" />
                </div>
              ) : (
                users.map(u => (
                  <label
                    key={u.id}
                    className={clsx(
                      'flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors',
                      selectedIds.includes(u.id)
                        ? 'bg-[var(--hf-status-blue-badge)] border border-[color:var(--hf-status-blue-badge)]'
                        : 'hover:bg-[var(--hf-ui-hover)] border border-transparent'
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(u.id)}
                      onChange={() => toggleUser(u.id)}
                      className="w-4 h-4 rounded border-[var(--hf-ui-border)] text-[var(--hf-cyan-700)] focus:ring-[var(--hf-cyan-500)]"
                    />
                    <span className="text-sm">{u.name}</span>
                  </label>
                ))
              )}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-[var(--hf-ui-divider)]">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg text-[var(--hf-main-700)] hover:text-[var(--hf-main-900)] hover:bg-[var(--hf-ui-hover)] transition-colors"
          >
            Отмена
          </button>
          <button
            onClick={handleSave}
            disabled={loading || (!assignAll && selectedIds.length === 0)}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-[var(--hf-cyan-700)] text-[var(--hf-white)] hover:bg-[var(--hf-cyan-600)] disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
          >
            {loading ? (
              <div className="animate-spin w-4 h-4 border-2 border-[color:var(--hf-white)] border-t-transparent rounded-full" />
            ) : (
              <UserPlus className="w-4 h-4" />
            )}
            Назначить
          </button>
        </div>
      </div>
    </div>
  );
}
