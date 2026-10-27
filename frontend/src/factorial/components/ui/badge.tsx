import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/factorial/lib/cn';

const badgeVariants = cva(
  'inline-flex items-center rounded-pill border px-2.5 py-0.5 text-fx-xs font-medium transition-colors',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-status-active-bg text-status-active-text',
        primary: 'border-transparent bg-primary text-white',
        success: 'border-transparent bg-status-progress/15 text-status-progress',
        warning: 'border-transparent bg-status-pending/15 text-status-pending',
        danger: 'border-transparent bg-status-overdue/15 text-status-overdue',
        outline: 'border-border text-text-primary',
      },
    },
    defaultVariants: { variant: 'default' },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
