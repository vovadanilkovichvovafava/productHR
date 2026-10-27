import { ReactNode, useState } from 'react';
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import { Filter } from 'lucide-react';
import { format, addMonths, subMonths, startOfMonth, endOfMonth, startOfWeek, endOfWeek, eachDayOfInterval, isSameMonth, isToday, getDay } from 'date-fns';
import { ru } from 'date-fns/locale';
import { cn } from '@/factorial/lib/cn';
import PageHeader from '@/factorial/components/PageHeader';
import SecondaryNav from '@/factorial/components/SecondaryNav';

export interface CalendarEvent { id: number; date: string; title: string; color: string; }

interface CalendarTemplateProps {
  breadcrumb: { label: string; href?: string }[];
  titleIcon?: ReactNode;
  title?: string;
  secondaryNav?: { label: string; href: string; end?: boolean }[];
  events: CalendarEvent[];
  primaryCta?: { label: string; onClick: () => void };
  /** Опциональный блок между заголовком и сеткой календаря (например, счётчики отпуска). */
  headerExtra?: ReactNode;
}

export default function CalendarTemplate({ breadcrumb, titleIcon, title, secondaryNav, events, primaryCta, headerExtra }: CalendarTemplateProps) {
  const [currentMonth, setCurrentMonth] = useState(() => {
    const n = new Date();
    return new Date(n.getFullYear(), n.getMonth(), 1);
  });

  const start = startOfWeek(startOfMonth(currentMonth), { weekStartsOn: 1 });
  const end = endOfWeek(endOfMonth(currentMonth), { weekStartsOn: 1 });
  const days = eachDayOfInterval({ start, end });
  const weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

  const eventsByDay: Record<string, CalendarEvent[]> = {};
  events.forEach((e) => {
    const key = e.date.slice(0, 10);
    eventsByDay[key] = [...(eventsByDay[key] || []), e];
  });

  return (
    <>
      <PageHeader breadcrumb={breadcrumb} />
      <div className="px-8 py-6 space-y-5">
        {(titleIcon || title) && (
          <div className="flex items-center gap-2">
            {titleIcon}
            {title && <h1 className="text-fx-xl font-semibold">{title}</h1>}
          </div>
        )}
        {secondaryNav && <SecondaryNav items={secondaryNav} />}
        {headerExtra}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button type="button" className="p-2 rounded-fx-lg border border-border bg-white hover:bg-sidebar-hover">
              <Filter className="w-4 h-4 text-text-muted" />
            </button>
            <div className="flex items-center gap-1 bg-white border border-border rounded-fx-lg">
              <button type="button" onClick={() => setCurrentMonth(subMonths(currentMonth, 1))} className="p-2 hover:bg-sidebar-hover rounded-l-lg">
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-3 text-fx-sm font-medium min-w-[120px] text-center">
                {format(currentMonth, 'LLLL yyyy', { locale: ru })}
              </span>
              <button type="button" onClick={() => setCurrentMonth(addMonths(currentMonth, 1))} className="p-2 hover:bg-sidebar-hover rounded-r-lg">
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
            <button type="button" onClick={() => setCurrentMonth(new Date())} className="px-3 py-2 text-fx-sm font-medium border border-border bg-white rounded-fx-lg hover:bg-sidebar-hover">
              Сегодня
            </button>
          </div>
          {primaryCta && (
            <button type="button" onClick={primaryCta.onClick} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-2xl border border-card-border-soft bg-white hover:bg-sidebar-hover text-text-primary text-fx-base font-normal">
              <Plus className="w-4 h-4" /> {primaryCta.label}
            </button>
          )}
        </div>

        <div className="bg-white rounded-card shadow-card border border-border overflow-hidden">
          <div className="grid grid-cols-7 text-center text-fx-xs font-medium text-text-muted border-b border-border">
            {weekdays.map((wd) => <div key={wd} className="py-2">{wd}</div>)}
          </div>
          <div className="grid grid-cols-7">
            {days.map((d) => {
              const key = format(d, 'yyyy-MM-dd');
              const dayEvents = eventsByDay[key] || [];
              const inMonth = isSameMonth(d, currentMonth);
              const isSunday = getDay(d) === 0;
              return (
                <div key={key} className={cn(
                  'min-h-[100px] border-r border-b border-card-border-soft p-2 flex flex-col gap-1',
                  !inMonth && 'bg-app-bg/40',
                )}>
                  <span className={cn(
                    'text-fx-xs font-medium self-end',
                    !inMonth && 'text-text-muted/50',
                    inMonth && isSunday && !isToday(d) && 'text-primary',
                    isToday(d) && 'bg-primary text-white rounded-full w-5 h-5 flex items-center justify-center'
                  )}>
                    {format(d, 'd')}
                  </span>
                  {dayEvents.map((e) => (
                    <div key={e.id} className="text-fx-xs px-1.5 py-0.5 rounded truncate" style={{ background: e.color + '20', color: e.color }}>
                      {e.title}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </>
  );
}
