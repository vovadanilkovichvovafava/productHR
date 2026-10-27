import { ArrowRight, Pencil, Plus, Heart, ChevronDown } from 'lucide-react';
import { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import PageHeader from '@/factorial/components/PageHeader';
import BirthdayCard from '@/factorial/components/BirthdayCard';
import UserAvatar from '@/factorial/components/UserAvatar';
import { currentUser } from '@/factorial/mocks/currentUser';
import { todayBirthdays } from '@/factorial/mocks/communityPosts';

function getGreeting(): string {
  const h = new Date().getHours();
  if (h >= 5 && h < 12) return 'Доброе утро';
  if (h >= 12 && h < 18) return 'Добрый день';
  if (h >= 18 && h < 23) return 'Добрый вечер';
  return 'Доброй ночи';
}

export default function DashboardTemplate() {
  const navigate = useNavigate();
  const greeting = getGreeting();
  return (
    <>
      <PageHeader breadcrumb={[]} />
      <div className="px-8 py-6 space-y-8">
        <div className="flex items-center gap-3">
          <UserAvatar fullName={currentUser.fullName} size="md" />
          <h1 className="text-fx-2xl font-semibold">{greeting}, {currentUser.position}!</h1>
        </div>

        <div className="grid grid-cols-3 gap-6">
          <WidgetCard title="Входящие" emoji="☕️" heading="Отлично справились!" description="Входящие пусты." icon={<ArrowRight className="w-4 h-4" />} />
          <WidgetCard
            title="Ивенты"
            emoji="📅"
            heading="На горизонте пусто"
            description="Оставайтесь на связи!"
            icon={<ArrowRight className="w-4 h-4" />}
            cta={
              <button type="button" onClick={() => navigate('/factorial/dashboard/event/new')} className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 text-fx-xs font-medium border border-border rounded-fx-lg hover:bg-sidebar-hover">
                <Plus className="w-3 h-3" /> Добавить событие
              </button>
            }
          />
          <WidgetCard title="Ссылки" emoji="🔗" heading="Давайте свяжемся!" description="Делитесь ценными ресурсами." icon={<Pencil className="w-4 h-4" />} />
        </div>

        <section>
          <h2 className="text-[22px] font-semibold mb-3 leading-tight">Сегодня в {currentUser.company}</h2>
          <div className="flex gap-4">
            {todayBirthdays.map((b) => <BirthdayCard key={b.id} item={b} />)}
          </div>
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <button type="button" className="flex items-center gap-1 text-fx-sm font-normal text-text-primary">
              Все сообщества <ChevronDown className="w-4 h-4" />
            </button>
            <button type="button" onClick={() => navigate('/factorial/dashboard/post/new')} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-fx-xs font-medium border border-border rounded-fx-lg hover:bg-sidebar-hover">
              <Pencil className="w-3 h-3" /> Написать пост
            </button>
          </div>
          <div className="bg-love-banner rounded-card p-5 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-white/80 flex items-center justify-center">
                <Heart className="w-5 h-5 text-pink-500 fill-pink-500" />
              </div>
              <div>
                <p className="text-fx-sm font-semibold">Поблагодарите команду за отличную работу!</p>
                <p className="text-fx-xs text-text-muted">Выразите признательность и распространяйте позитив</p>
              </div>
            </div>
            <button type="button" onClick={() => navigate('/factorial/dashboard/kudos/new')} className="px-4 py-2 text-fx-sm font-medium border border-border bg-white rounded-fx-lg hover:bg-sidebar-hover">
              Поделитесь любовью
            </button>
          </div>
        </section>
      </div>
    </>
  );
}

function WidgetCard({ title, emoji, heading, description, icon, cta }: {
  title: string; emoji: string; heading: string; description: string; icon: ReactNode; cta?: ReactNode;
}) {
  return (
    <div className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5 min-h-[260px] flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-fx-sm font-medium">{title}</h3>
        <button type="button" className="p-1 rounded hover:bg-sidebar-hover text-text-muted">{icon}</button>
      </div>
      <div className="flex-1 flex flex-col items-center justify-center text-center gap-2">
        <div className="text-fx-4xl">{emoji}</div>
        <p className="text-fx-sm font-semibold">{heading}</p>
        <p className="text-fx-xs text-text-muted">{description}</p>
        {cta}
      </div>
    </div>
  );
}
