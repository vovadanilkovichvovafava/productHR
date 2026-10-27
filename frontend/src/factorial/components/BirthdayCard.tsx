import { format } from 'date-fns';
import UserAvatar from './UserAvatar';
import type { BirthdayItem } from '@/factorial/mocks/communityPosts';

export default function BirthdayCard({ item }: { item: BirthdayItem }) {
  const d = new Date(item.date);
  const month = format(d, 'MMM').toUpperCase();
  const day = format(d, 'd');
  return (
    <div className="w-60 bg-white rounded-card shadow-card p-4 flex flex-col gap-3 relative">
      <div className="bg-gradient-to-br from-violet-100 to-violet-50 rounded-card aspect-square flex items-center justify-center relative">
        <UserAvatar fullName={item.fullName} size="xl" />
        <div className="absolute bottom-2 right-2 w-7 h-7 rounded-full bg-white shadow flex items-center justify-center text-fx-sm">
          {item.emoji}
        </div>
      </div>
      <div>
        <p className="text-fx-sm font-semibold truncate">{item.fullName}</p>
        <div className="flex items-center justify-between mt-0.5">
          <span className="text-fx-xs text-text-muted truncate">{item.eventLabel} {item.emoji}</span>
          <div className="flex flex-col items-center bg-red-50 text-red-700 rounded px-1.5 py-0.5">
            <span className="text-[9px] font-bold uppercase leading-none">{month}</span>
            <span className="text-fx-xs font-bold leading-none">{day}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
