import { Link } from 'react-router-dom';
import type { SignedDoc } from '@/factorial/api/types';

export default function MyDocsMini({ docs }: { docs: SignedDoc[] }) {
  const latest = [...docs]
    .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
    .slice(0, 5);
  return (
    <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Мои документы</h2>
        <Link to="/factorial/my-documents" className="text-fx-sm text-text-secondary hover:text-text-primary">
          Все
        </Link>
      </div>
      {latest.length === 0 ? (
        <div className="text-fx-sm text-text-muted py-2">Документов пока нет</div>
      ) : (
        <ul className="divide-y divide-card-border-soft">
          {latest.map((d) => (
            <li key={d.id} className="flex items-center justify-between py-2 text-fx-sm">
              <span className="truncate">{d.title}</span>
              <span className={(d.status === 'signed' ? 'text-emerald-600' : 'text-amber-600') + ' shrink-0 ml-3'}>
                {d.status === 'signed' ? 'Подписан' : 'На подпись'}
              </span>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
