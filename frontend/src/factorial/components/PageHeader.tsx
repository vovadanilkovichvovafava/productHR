import { ReactNode } from 'react';
import Breadcrumb from './Breadcrumb';

interface PageHeaderProps {
  breadcrumb: { label: string; href?: string }[];
  rightContent?: ReactNode;
}

// Кнопки «Уведомления» (ничего не делала) и «Открыть Опе» (открывала
// несмонтированный чат и исчезала навсегда) убраны 27.10.2026.
export default function PageHeader({ breadcrumb, rightContent }: PageHeaderProps) {
  return (
    <div className="flex items-center justify-between px-8 py-4 border-b border-border bg-white/40 backdrop-blur-sm sticky top-0 z-10">
      <Breadcrumb items={breadcrumb} />
      {rightContent && <div className="flex items-center gap-3">{rightContent}</div>}
    </div>
  );
}
