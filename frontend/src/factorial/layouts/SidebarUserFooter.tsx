import { Bell } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useSidebarStore } from '@/factorial/stores/useSidebarStore';
import { currentUser } from '@/factorial/mocks/currentUser';
import { colors } from '@/factorial/lib/tokens';
import { getMyProfile } from '@/factorial/api/employees';

export default function SidebarUserFooter() {
  const collapsed = useSidebarStore((s) => s.collapsed);
  // Реальный текущий пользователь; при отсутствии Employee-записи — мок-фолбэк.
  const { data: me } = useQuery({ queryKey: ['fx', 'me'], queryFn: getMyProfile, retry: false });
  const fullName = me?.user_name || currentUser.fullName;
  const initials = me?.user_name
    ? me.user_name.trim().split(/\s+/).slice(0, 2).map((w) => w[0] || '').join('').toUpperCase()
    : currentUser.initials;
  const palette = colors.avatarPalette[currentUser.avatarColorIndex];

  return (
    <div className="flex items-center gap-2">
      <div
        style={{ background: palette.bg, color: palette.fg }}
        className="w-8 h-8 rounded-full flex items-center justify-center text-fx-xs font-semibold shrink-0"
      >
        {initials}
      </div>
      {!collapsed && (
        <>
          <span className="flex-1 text-fx-sm font-medium truncate">{fullName}</span>
          <button
            type="button"
            className="p-1 rounded hover:bg-sidebar-hover transition-colors"
            onClick={() => window.alert('Уведомления: 0 новых.')}
            aria-label="Уведомления"
          >
            <Bell className="w-4 h-4 text-text-muted" strokeWidth={1.5} />
          </button>
        </>
      )}
    </div>
  );
}
