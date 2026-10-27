import { BookOpen } from 'lucide-react';
import FeedTemplate from '@/factorial/templates/FeedTemplate';
import { policies } from '@/factorial/mocks/policies';
import { formatDateRu } from '@/factorial/lib/formatDate';

export default function PagesPage() {
  return (
    <FeedTemplate
      breadcrumb={[{ label: 'Политики' }]}
      titleIcon={
        <div className="w-9 h-9 rounded-fx-lg bg-indigo-100 flex items-center justify-center">
          <BookOpen className="w-5 h-5 text-indigo-600" />
        </div>
      }
      title="Политики"
      items={policies.map((p) => (
        <article key={p.id} className="bg-white rounded-card border border-border p-5 flex items-start gap-3 hover:shadow-card-hover transition-shadow cursor-pointer"
          onClick={() => alert('Demo mode — открыть политику')}>
          <BookOpen className="w-5 h-5 text-text-muted mt-0.5" />
          <div>
            <h3 className="font-semibold">{p.title}</h3>
            <p className="text-fx-xs text-text-muted mt-0.5">Обновлено {formatDateRu(p.updatedAt)} · автор {p.author}</p>
          </div>
        </article>
      ))}
    />
  );
}
