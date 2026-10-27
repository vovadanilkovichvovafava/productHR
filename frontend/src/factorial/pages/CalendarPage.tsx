import { Calendar as CalendarIcon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import CalendarTemplate from '@/factorial/templates/CalendarTemplate';
import { timeOffEvents } from '@/factorial/mocks/timeOff';

export default function CalendarPage() {
  const navigate = useNavigate();
  return (
    <CalendarTemplate
      breadcrumb={[{ label: 'Календарь' }]}
      titleIcon={<div className="w-9 h-9 rounded-fx-lg bg-red-100 flex items-center justify-center"><CalendarIcon className="w-5 h-5 text-red-600" /></div>}
      title="Календарь"
      secondaryNav={[
        { label: 'Календарь', href: '/factorial/calendar', end: true },
        { label: 'Обзор команды', href: '/factorial/calendar/team-view' },
      ]}
      events={timeOffEvents}
      primaryCta={{ label: 'Добавить отпуск', onClick: () => navigate('/factorial/calendar/add-time-off') }}
    />
  );
}
