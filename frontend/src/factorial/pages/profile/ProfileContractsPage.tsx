import { User } from 'lucide-react';
import ProfileTemplate from '@/factorial/templates/ProfileTemplate';
import EmptyState from '@/factorial/components/EmptyState';
import { PROFILE_SUBNAV } from './_subNav';

export default function ProfileContractsPage() {
  return (
    <ProfileTemplate
      breadcrumb={[{ label: 'Профиль' }, { label: 'Соглашения' }]}
      titleIcon={<div className="w-9 h-9 rounded-fx-lg bg-pink-100 flex items-center justify-center"><User className="w-5 h-5 text-pink-600" /></div>}
      title="Профиль"
      subNav={PROFILE_SUBNAV}
      leftColumn={<div className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-12"><EmptyState emoji="🚧" heading="Раздел в разработке" description="Будет реализовано в следующих фазах." /></div>}
      rightDetails={[]}
    />
  );
}
