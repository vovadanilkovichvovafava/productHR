import type { LeaveBalance } from '@/factorial/api/types';

const ROWS: { key: 'vacation' | 'sick' | 'family_leave'; label: string; color: string }[] = [
  { key: 'vacation', label: 'Отпуск', color: '#16A34A' },
  { key: 'sick', label: 'Больничный', color: '#DC2626' },
  { key: 'family_leave', label: 'Семейные дни', color: '#2563EB' },
];

export default function LeaveBalanceCard({
  balance,
  onRequest,
}: {
  balance?: LeaveBalance;
  onRequest: () => void;
}) {
  return (
    <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Баланс отпусков</h2>
        <button
          type="button"
          onClick={onRequest}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-fx-xs font-medium border border-card-border-soft rounded-fx-lg hover:bg-sidebar-hover"
        >
          Запросить отпуск
        </button>
      </div>
      {!balance ? (
        <div className="text-fx-sm text-text-muted py-2">—</div>
      ) : (
        <div className="space-y-3">
          {ROWS.map((r) => {
            const b = balance as unknown as Record<string, number>;
            const total = b[`${r.key}_total`] ?? 0;
            const used = b[`${r.key}_used`] ?? 0;
            const remaining = b[`${r.key}_remaining`] ?? Math.max(0, total - used);
            const pct = total > 0 ? Math.round((remaining / total) * 100) : 0;
            return (
              <div key={r.key}>
                <div className="flex items-center justify-between text-fx-sm">
                  <span>{r.label}</span>
                  <span className="text-text-muted">{remaining} из {total} дн.</span>
                </div>
                <div className="h-2 mt-1 rounded-pill bg-app-bg overflow-hidden">
                  <div className="h-full rounded-pill" style={{ width: `${pct}%`, background: r.color }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </article>
  );
}
