import clsx from 'clsx';

interface SkeletonProps {
  className?: string;
  variant?: 'text' | 'circular' | 'rectangular' | 'rounded';
  width?: string | number;
  height?: string | number;
  animation?: 'pulse' | 'wave' | 'none';
}

export function Skeleton({
  className,
  variant = 'rectangular',
  width,
  height,
  animation = 'pulse'
}: SkeletonProps) {
  const baseStyles = 'bg-white/10';

  const variantStyles = {
    text: 'rounded',
    circular: 'rounded-full',
    rectangular: '',
    rounded: 'rounded-lg'
  };

  const animationStyles = {
    pulse: 'animate-pulse',
    wave: 'animate-shimmer',
    none: ''
  };

  return (
    <div
      className={clsx(
        baseStyles,
        variantStyles[variant],
        animationStyles[animation],
        className
      )}
      style={{
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof height === 'number' ? `${height}px` : height
      }}
    />
  );
}

// Pre-built skeleton patterns

export function VacancyCardSkeleton() {
  return (
    <div className="p-4 glass-light rounded-xl animate-pulse">
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <Skeleton variant="text" className="h-6 w-3/4 mb-2" />
          <Skeleton variant="text" className="h-4 w-20" />
        </div>
        <Skeleton variant="rounded" className="h-5 w-16" />
      </div>
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Skeleton variant="circular" width={16} height={16} />
          <Skeleton variant="text" className="h-4 w-24" />
        </div>
        <div className="flex items-center gap-2">
          <Skeleton variant="circular" width={16} height={16} />
          <Skeleton variant="text" className="h-4 w-32" />
        </div>
      </div>
      <div className="mt-4 pt-3 border-t border-white/10 flex items-center justify-between">
        <Skeleton variant="text" className="h-4 w-28" />
        <div className="flex gap-1">
          <Skeleton variant="rounded" className="h-5 w-8" />
          <Skeleton variant="rounded" className="h-5 w-8" />
        </div>
      </div>
    </div>
  );
}

export function EntityCardSkeleton() {
  return (
    <div className="p-4 glass-light rounded-xl animate-pulse">
      <div className="flex items-center gap-3 mb-3">
        <Skeleton variant="circular" width={40} height={40} />
        <div className="flex-1">
          <Skeleton variant="text" className="h-5 w-32 mb-1" />
          <Skeleton variant="text" className="h-4 w-24" />
        </div>
        <Skeleton variant="rounded" className="h-5 w-16" />
      </div>
      <div className="space-y-2">
        <Skeleton variant="text" className="h-4 w-full" />
        <Skeleton variant="text" className="h-4 w-2/3" />
      </div>
      <div className="mt-3 flex gap-1">
        <Skeleton variant="rounded" className="h-5 w-12" />
        <Skeleton variant="rounded" className="h-5 w-14" />
        <Skeleton variant="rounded" className="h-5 w-10" />
      </div>
    </div>
  );
}

export function KanbanCardSkeleton() {
  return (
    <div className="p-3 bg-gray-800 rounded-lg border border-white/10 animate-pulse">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex-1">
          <Skeleton variant="text" className="h-5 w-28 mb-1" />
          <Skeleton variant="text" className="h-3 w-20" />
        </div>
      </div>
      <div className="space-y-1">
        <div className="flex items-center gap-1.5">
          <Skeleton variant="circular" width={12} height={12} />
          <Skeleton variant="text" className="h-3 w-32" />
        </div>
        <div className="flex items-center gap-1.5">
          <Skeleton variant="circular" width={12} height={12} />
          <Skeleton variant="text" className="h-3 w-24" />
        </div>
      </div>
      <div className="flex items-center justify-between mt-3 pt-2 border-t border-white/5">
        <Skeleton variant="rounded" className="h-4 w-8" />
        <Skeleton variant="text" className="h-3 w-16" />
      </div>
    </div>
  );
}

export function TableRowSkeleton({ columns = 5 }: { columns?: number }) {
  return (
    <tr className="border-b border-white/10 animate-pulse">
      {Array.from({ length: columns }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <Skeleton
            variant="text"
            className="h-4"
            width={i === 0 ? '60%' : i === columns - 1 ? '30%' : '80%'}
          />
        </td>
      ))}
    </tr>
  );
}

export function DetailSkeleton() {
  return (
    <div className="p-6 space-y-6 animate-pulse">
      <div className="flex items-center gap-4">
        <Skeleton variant="circular" width={64} height={64} />
        <div className="flex-1">
          <Skeleton variant="text" className="h-8 w-48 mb-2" />
          <Skeleton variant="text" className="h-5 w-32" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="p-4 glass-light rounded-xl">
            <Skeleton variant="text" className="h-4 w-20 mb-2" />
            <Skeleton variant="text" className="h-6 w-28" />
          </div>
        ))}
      </div>
      <div className="p-6 glass-light rounded-xl">
        <Skeleton variant="text" className="h-6 w-32 mb-4" />
        <div className="space-y-2">
          <Skeleton variant="text" className="h-4 w-full" />
          <Skeleton variant="text" className="h-4 w-full" />
          <Skeleton variant="text" className="h-4 w-2/3" />
        </div>
      </div>
    </div>
  );
}

export function ListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="p-4 glass-light rounded-xl animate-pulse">
          <div className="flex items-center gap-3">
            <Skeleton variant="circular" width={40} height={40} />
            <div className="flex-1">
              <Skeleton variant="text" className="h-5 w-40 mb-1" />
              <Skeleton variant="text" className="h-4 w-24" />
            </div>
            <Skeleton variant="text" className="h-4 w-16" />
          </div>
        </div>
      ))}
    </div>
  );
}
