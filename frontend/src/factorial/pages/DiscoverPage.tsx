import { Megaphone } from 'lucide-react';
import FeedTemplate from '@/factorial/templates/FeedTemplate';

export default function DiscoverPage() {
  return (
    <FeedTemplate
      breadcrumb={[{ label: 'Что нового' }]}
      titleIcon={
        <div className="w-9 h-9 rounded-fx-lg bg-sky-100 flex items-center justify-center">
          <Megaphone className="w-5 h-5 text-sky-600" />
        </div>
      }
      title="Что нового"
      emptyState={{ emoji: '📢', heading: 'Скоро здесь будет что-то новое', description: 'Подпишитесь на обновления Factorial.' }}
    />
  );
}
