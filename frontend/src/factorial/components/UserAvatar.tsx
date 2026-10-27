import { cn } from '@/factorial/lib/cn';
import { getAvatarPalette, getInitials } from '@/factorial/lib/avatarColor';

interface UserAvatarProps {
  fullName: string;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
  /** Show only the first letter (Factorial uses this in the employees table). */
  singleLetter?: boolean;
}

const SIZES = { xs: 'w-6 h-6 text-[10px]', sm: 'w-7 h-7 text-fx-xs', md: 'w-8 h-8 text-fx-xs', lg: 'w-12 h-12 text-fx-base', xl: 'w-24 h-24 text-fx-2xl' };

export default function UserAvatar({ fullName, size = 'md', className, singleLetter }: UserAvatarProps) {
  const palette = getAvatarPalette(fullName);
  const initials = singleLetter
    ? (fullName.trim()[0] || '').toUpperCase()
    : getInitials(fullName);
  return (
    <div
      style={{ background: palette.bg, color: palette.fg }}
      className={cn('rounded-full flex items-center justify-center font-semibold shrink-0', SIZES[size], className)}
      title={fullName}
    >
      {initials}
    </div>
  );
}
